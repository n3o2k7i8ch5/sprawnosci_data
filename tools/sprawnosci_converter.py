#!/usr/bin/env python3
"""
Converts Dart SprawBookData files (ZHP 2022) into the YAML assets structure
like assets/sprawnosci/zhr_harc_c_sim_2023.

Usage:
  python tools/sprawnosci_converter.py \
    --dart /path/to/lib/sprawnosci/tmp/data_spraw_zhp_harc_sim_2022.dart \
    --out assets/sprawnosci/zhp_harc_sim_2022

You can run it twice for the zuch file too, e.g.:
  python tools/sprawnosci_converter.py \
    --dart lib/sprawnosci/tmp/data_spraw_zhp_zuch_sim_2022.dart \
    --out assets/sprawnosci/zhp_zuch_sim_2022

Notes:
- The script infers schema from example assets. It emits:
  - book/_data.yaml with slug and name
  - group{n}@<group_id>/_data.yaml with slug and name
  - family{m}@<family_id>/_data.yaml with slug and name (optional tags omitted)
  - <level>@<id>$<level>/_data.yaml with slug, name, level, tasks
- It ignores icons, literary fragments, and comments because they are not present
  in the Dart sources or not mapped in the example schema.
"""

import argparse
import os
import re
import shutil
import sys
from typing import List, Dict, Any, Optional, Tuple

# --- Parsing helpers ---------------------------------------------------------

STRING_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")
KEY_RE = re.compile(r"(\w+)\s*:\s*(.*)")


def unescape_dart_string(s: str) -> str:
    """Unescape Dart string literals while preserving UTF-8 characters like Polish ą, ę, etc."""
    # Handle common Dart escape sequences manually to avoid corrupting UTF-8
    s = s.replace('\\n', '\n')
    s = s.replace('\\r', '\r')
    s = s.replace('\\t', '\t')
    s = s.replace("\\'", "'")
    s = s.replace('\\"', '"')
    s = s.replace('\\\\', '\\')
    return s


def count_parens_outside_strings(line: str) -> Tuple[int, int]:
    """Count parentheses outside of string literals. Returns (open_count, close_count)."""
    # Remove all string literals to avoid counting parens inside them
    cleaned = STRING_RE.sub('', line)
    return cleaned.count('('), cleaned.count(')')


def find_blocks(src: List[str], start_token: str) -> List[Tuple[int, int]]:
    """Find top-level blocks starting with e.g. 'SprawGroupData(' and return (start, end) line indexes inclusive."""
    blocks = []
    depth = 0
    start_idx = None
    token = start_token
    for i, line in enumerate(src):
        if token in line and start_idx is None:
            # found start of a block
            start_idx = i
            open_p, close_p = count_parens_outside_strings(line)
            depth = open_p - close_p
            if depth <= 0:
                # single-line block
                blocks.append((start_idx, i))
                start_idx = None
            continue
        if start_idx is not None:
            open_p, close_p = count_parens_outside_strings(line)
            depth += open_p - close_p
            if depth <= 0:
                blocks.append((start_idx, i))
                start_idx = None
    return blocks


def parse_string_list(lines: List[str], start_i: int) -> Tuple[List[str], int]:
    """Parse a Dart list of string literals possibly split into adjacent literals.
    Returns (list, next_line_index_after_list).
    """
    items: List[str] = []
    i = start_i
    # Expect the current line contains '[' or starts at the line with '[' already read
    # Accumulate until matching closing ']' encountered (balance nested brackets just in case)
    bracket_depth = 0
    # find first '['
    while i < len(lines) and '[' not in lines[i]:
        i += 1
    if i >= len(lines):
        return items, i
    # Start after finding first '['
    bracket_depth += lines[i].count('[')
    bracket_depth -= lines[i].count(']')
    current_parts: List[str] = []
    
    # Parse strings on the same line as '[' if present
    first_line_literals = STRING_RE.findall(lines[i])
    if first_line_literals:
        for lit in first_line_literals:
            items.append(unescape_dart_string(lit))
    
    # If list is complete on one line, return early
    if bracket_depth <= 0:
        return [s.strip() for s in items if s.strip()], i + 1
    
    i += 1
    while i < len(lines):
        line = lines[i].rstrip()
        bracket_depth += line.count('[')
        bracket_depth -= line.count(']')

        # Extract all string literals in this line
        literals = STRING_RE.findall(line)
        if literals:
            # If line ends with a comma, that closes the current item
            # Dart allows adjacent string literals: we concatenate all in this line
            concat = ''.join(unescape_dart_string(x) for x in literals)
            current_parts.append(concat)
            # If there's a trailing comma outside of string literals, or next line starts new quoted string with trailing comma,
            # we decide end-of-item by a comma at end or by next line starting with non-string item or end of list.
            # Heuristic: if line.strip().endswith(',') and not line.strip().endswith("',") due to matching above, still okay.
            if line.strip().endswith(','):
                items.append(''.join(current_parts))
                current_parts = []
        else:
            # No string literal on this line. If we have accumulated parts and this line is just a comma, close item.
            if current_parts and line.strip() == ',':
                items.append(''.join(current_parts))
                current_parts = []

        if bracket_depth <= 0:
            # end of list
            if current_parts:
                items.append(''.join(current_parts))
                current_parts = []
            i += 1
            break
        i += 1
    return [s.strip() for s in items if s.strip()], i


def parse_key_value(line: str) -> Optional[Tuple[str, str]]:
    m = KEY_RE.search(line)
    if not m:
        return None
    return m.group(1), m.group(2)


# --- High-level parsing ------------------------------------------------------

def parse_spraw_book(dart_text: str) -> Dict[str, Any]:
    lines = dart_text.splitlines()
    # Extract book title for top-level _data.yaml
    title = None
    book_id = None
    org = None
    for line in lines[:200]:
        if 'title:' in line and title is None:
            # title: 'Sprawności harcerskie ZHP',
            lit = STRING_RE.search(line)
            if lit:
                title = unescape_dart_string(lit.group(1))
        if 'id:' in line and 'SprawBookData.' in line and book_id is None:
            # id: SprawBookData.zhpHarcSim2022Id,
            m = re.search(r"SprawBookData\.([a-zA-Z0-9_]+)", line)
            if m:
                book_id = m.group(1)
        if 'org:' in line and org is None:
            m = re.search(r"Org\.([a-zA-Z0-9_]+)", line)
            if m:
                org = m.group(1)
    if not title:
        title = 'Sprawności'
    if not book_id:
        # Fallback to slug from filename caller should set as output dir name
        book_id = 'book'

    # Parse groups
    groups: List[Dict[str, Any]] = []
    group_blocks = find_blocks(lines, 'SprawGroupData(')
    for g_start, g_end in group_blocks:
        g_lines = lines[g_start:g_end+1]
        group_id = None
        group_title = None
        group_description = None
        group_tags: List[str] = []
        families: List[Dict[str, Any]] = []
        # basic fields
        for gl in g_lines[:30]:
            if 'id:' in gl and group_id is None:
                lit = STRING_RE.search(gl)
                if lit:
                    group_id = unescape_dart_string(lit.group(1))
            if 'title:' in gl and group_title is None:
                lit = STRING_RE.search(gl)
                if lit:
                    group_title = unescape_dart_string(lit.group(1))
            if 'description:' in gl and group_description is None:
                lit = STRING_RE.search(gl)
                if lit:
                    group_description = unescape_dart_string(lit.group(1))
        # find tags for group (only at group level, before families)
        # Find the first family block to limit search scope
        first_fam_idx = next((i for i, l in enumerate(g_lines) if 'SprawFamilyData(' in l), len(g_lines))
        # Look for 'tags:' in the group header (before first family, typically in first 20 lines)
        search_limit = min(first_fam_idx, 20)
        tags_idx = next((i for i, l in enumerate(g_lines[:search_limit]) if re.search(r'^\s*tags\s*:', l)), -1)
        if tags_idx != -1:
            # Parse only within the limited scope to avoid picking up family data
            lst, _next = parse_string_list(g_lines[:search_limit + 10], tags_idx)
            group_tags = lst
        # families within this group
        fam_blocks = find_blocks(g_lines, 'SprawFamilyData(')
        for f_start_rel, f_end_rel in fam_blocks:
            f_lines = g_lines[f_start_rel:f_end_rel+1]
            fam_id = None
            fam_tags: List[str] = []
            fam_fragment = None
            fam_fragment_author = None
            # optional arrays
            notes_for_leaders: List[str] = []
            requirements: List[str] = []
            # find id and other simple fields
            for fl in f_lines[:20]:
                if 'id:' in fl and fam_id is None:
                    lit = STRING_RE.search(fl)
                    if lit:
                        fam_id = unescape_dart_string(lit.group(1))
                if 'fragment:' in fl and fam_fragment is None:
                    lit = STRING_RE.search(fl)
                    if lit:
                        fam_fragment = unescape_dart_string(lit.group(1))
                if 'fragmentAuthor:' in fl and fam_fragment_author is None:
                    lit = STRING_RE.search(fl)
                    if lit:
                        fam_fragment_author = unescape_dart_string(lit.group(1))
            # find notesForLeaders
            nfl_idx = next((i for i, l in enumerate(f_lines) if 'notesForLeaders' in l), -1)
            if nfl_idx != -1:
                lst, _next = parse_string_list(f_lines, nfl_idx)
                notes_for_leaders = lst
            req_idx = next((i for i, l in enumerate(f_lines) if 'requirements' in l), -1)
            if req_idx != -1:
                lst, _next = parse_string_list(f_lines, req_idx)
                requirements = lst
            # find tags for family (before first SprawData)
            first_spraw_idx = next((i for i, l in enumerate(f_lines) if 'SprawData(' in l), len(f_lines))
            fam_tags_idx = next((i for i, l in enumerate(f_lines[:first_spraw_idx]) if re.search(r'^\s*tags\s*:', l)), -1)
            if fam_tags_idx != -1:
                lst, _next = parse_string_list(f_lines[:first_spraw_idx + 10], fam_tags_idx)
                fam_tags = lst

            # parse SprawData blocks (levels)
            levels: List[Dict[str, Any]] = []
            spraw_blocks = find_blocks(f_lines, 'SprawData(')
            for s_start_rel, s_end_rel in spraw_blocks:
                s_lines = f_lines[s_start_rel:s_end_rel+1]
                s_id = None
                s_title = None
                s_level = None
                s_comment = None
                s_tasks_are_examples = False
                s_tasks: List[str] = []
                s_hidden_titles: List[str] = []
                # comment and tasksAreExamples optional
                # Parse simple fields
                comment_idx = -1
                for i, sl in enumerate(s_lines[:20]):
                    if 'id:' in sl and s_id is None:
                        lit = STRING_RE.search(sl)
                        if lit:
                            s_id = unescape_dart_string(lit.group(1))
                    if 'title:' in sl and s_title is None:
                        lit = STRING_RE.search(sl)
                        if lit:
                            s_title = unescape_dart_string(lit.group(1))
                    if 'level:' in sl and s_level is None:
                        m = re.search(r"level:\s*(\d+)", sl)
                        if m:
                            s_level = int(m.group(1))
                    if 'comment:' in sl and s_comment is None:
                        comment_idx = i
                    if 'tasksAreExamples:' in sl:
                        if 'true' in sl:
                            s_tasks_are_examples = True
                
                # Parse comment field (may span multiple lines with adjacent string literals)
                if comment_idx != -1:
                    comment_parts = []
                    # Find all string literals starting from comment line
                    i = comment_idx
                    # Get strings from the comment: line itself
                    literals = STRING_RE.findall(s_lines[i])
                    for lit in literals:
                        comment_parts.append(unescape_dart_string(lit))
                    i += 1
                    # Continue collecting adjacent string literals on following lines
                    while i < len(s_lines):
                        line = s_lines[i].strip()
                        # Stop if we hit a comma (end of comment field) or another field
                        if line.endswith(',') and not line.endswith("',"):
                            break
                        if ':' in line and not line.strip().startswith("'"):
                            # Hit another field
                            break
                        # Check for string literals
                        literals = STRING_RE.findall(s_lines[i])
                        if literals:
                            for lit in literals:
                                comment_parts.append(unescape_dart_string(lit))
                            # If this line ends with comma after the string, we're done
                            if s_lines[i].rstrip().endswith(','):
                                break
                        else:
                            # No more string literals
                            break
                        i += 1
                    if comment_parts:
                        s_comment = ''.join(comment_parts)
                # hiddenTitles
                ht_idx = next((i for i, l in enumerate(s_lines) if re.search(r'\bhiddenTitles\s*:', l)), -1)
                if ht_idx != -1:
                    hidden_titles, _next = parse_string_list(s_lines, ht_idx)
                    s_hidden_titles = hidden_titles
                # tasks
                t_idx = next((i for i, l in enumerate(s_lines) if re.search(r"\btasks\s*:\s*\[", l)), -1)
                if t_idx != -1:
                    tasks, _next = parse_string_list(s_lines, t_idx)
                    s_tasks = tasks
                if s_id and s_title and s_level is not None:
                    levels.append({
                        'id': s_id,
                        'title': s_title,
                        'level': s_level,
                        'comment': s_comment,
                        'tasksAreExamples': s_tasks_are_examples,
                        'tasks': s_tasks,
                        'hiddenNames': s_hidden_titles,
                    })
            # infer family title from any level title
            fam_title = None
            if levels:
                fam_title = levels[0]['title']
            families.append({
                'id': fam_id or 'family',
                'title': fam_title or (fam_id or 'Rodzina'),
                'tags': fam_tags,
                'fragment': fam_fragment,
                'fragmentAuthor': fam_fragment_author,
                'notesForLeaders': notes_for_leaders,
                'requirements': requirements,
                'levels': sorted(levels, key=lambda x: x['level'])
            })
        groups.append({
            'id': group_id or 'group',
            'title': group_title or (group_id or 'Grupa'),
            'description': group_description,
            'tags': group_tags,
            'families': families
        })

    return {
        'id': book_id,
        'title': title,
        'org': org,
        'groups': groups,
    }


# --- Writers -----------------------------------------------------------------

def write_text(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def yaml_escape(s: str) -> str:
    """Format a string for YAML, using literal block style for multi-line strings."""
    # If string contains newlines, use literal block style (|)
    if '\n' in s:
        # Use literal block style with proper indentation
        lines = s.split('\n')
        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()
        return '|\n' + '\n'.join('  ' + line for line in lines)
    else:
        # Single-line: use single-quote and escape single quotes by doubling
        return "'" + s.replace("'", "''") + "'"


def to_yaml_list(items: List[str], indent: int = 0) -> str:
    """Convert list of strings to YAML list format."""
    ind = ' ' * indent
    result = []
    for item in items:
        if '\n' in item:
            # Multi-line item: use literal block style
            lines = item.split('\n')
            # Remove trailing empty lines
            while lines and not lines[-1].strip():
                lines.pop()
            result.append(f"{ind}- |")
            for line in lines:
                result.append(f"{ind}  {line}")
        else:
            # Single-line item
            result.append(f"{ind}- {yaml_escape(item)}")
    return '\n'.join(result)


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip('_')
    return s or 'id'


def copy_icon(icons_dir: str, group_id: str, item_id: str, dest_dir: str):
    """Copy icon.svg from source directory to destination if it exists."""
    # Try to find the icon in the icons directory
    # Structure: icons_dir/group_id/item_id.svg
    source_path = os.path.join(icons_dir, group_id, f"{item_id}.svg")
    if os.path.exists(source_path):
        dest_path = os.path.join(dest_dir, 'icon.svg')
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(source_path, dest_path)
        print(f"  Copied icon: {item_id}.svg -> {dest_path}")
    else:
        print(f"  Warning: Icon not found: {source_path}")


def emit_assets(book: Dict[str, Any], out_dir: str, icons_dir: Optional[str] = None):
    # top-level _data.yaml
    book_id_guess = book['id'] or slugify(book['title'])
    write_text(os.path.join(out_dir, '_data.yaml'), f"slug: {book_id_guess}\nname: {book['title']}\n")

    # groups
    for gi, group in enumerate(book['groups'], start=1):
        group_id = group['id'] or f'group{gi}'
        group_dir = os.path.join(out_dir, f"group{gi}@{group_id}")
        group_yaml_lines = [f"slug: {group_id}", f"name: {group['title']}"]
        # Add description if present
        if group.get('description'):
            group_yaml_lines.append(f"description: {yaml_escape(group['description'])}")
        # Add tags if present
        if group.get('tags'):
            group_yaml_lines.append("")
            group_yaml_lines.append("tags:")
            for tag in group['tags']:
                group_yaml_lines.append(f"  - {yaml_escape(tag)}")
        group_yaml_lines.append("")
        write_text(os.path.join(group_dir, '_data.yaml'), '\n'.join(group_yaml_lines) + '\n')
        # families
        for fi, fam in enumerate(group['families'], start=1):
            fam_id = fam['id'] or f'family{fi}'
            fam_dir = os.path.join(group_dir, f"family{fi}@{fam_id}")
            fam_name = fam['title'] or fam_id
            fam_yaml = [f"slug: {fam_id}", f"name: {yaml_escape(fam_name)}", ""]
            
            # Add tags if present
            if fam.get('tags'):
                fam_yaml.append("tags:")
                for tag in fam['tags']:
                    fam_yaml.append(f"  - {yaml_escape(tag)}")
                fam_yaml.append("")
            
            # Add fragment if present
            if fam.get('fragment'):
                fam_yaml.append(f"fragment: {yaml_escape(fam['fragment'])}")
                fam_yaml.append("")
            
            # Add fragmentAuthor if present
            if fam.get('fragmentAuthor'):
                fam_yaml.append(f"fragmentAuthor: {yaml_escape(fam['fragmentAuthor'])}")
                fam_yaml.append("")
            
            # Add requirements if present
            if fam.get('requirements'):
                fam_yaml.append("requirements:")
                for req in fam['requirements']:
                    fam_yaml.append(f"  - {yaml_escape(req)}")
                fam_yaml.append("")
            
            # Add notesForLeaders if present
            if fam.get('notesForLeaders'):
                fam_yaml.append("notesForLeaders:")
                for note in fam['notesForLeaders']:
                    fam_yaml.append(f"  - {yaml_escape(note)}")
                fam_yaml.append("")
            
            write_text(os.path.join(fam_dir, '_data.yaml'), '\n'.join(fam_yaml) + '\n')
            # levels
            for level in fam['levels']:
                lvl = int(level['level'])
                item_id = level['id']
                item_name = level['title']
                item_dir = os.path.join(fam_dir, f"{lvl}@{item_id}${lvl}")
                lines = [
                    f"slug: {item_id}",
                    f"name: {yaml_escape(item_name)}",
                ]
                
                # Add hiddenNames if present
                if level.get('hiddenNames'):
                    lines.append("hiddenNames:")
                    for hidden_name in level['hiddenNames']:
                        lines.append(f"  - {yaml_escape(hidden_name)}")
                
                lines.append(f"level: {lvl}")
                
                # Add comment if present
                if level.get('comment'):
                    lines.append(f"comment: {yaml_escape(level['comment'])}")
                
                # Add tasksAreExamples if true
                if level.get('tasksAreExamples'):
                    lines.append("tasksAreExamples: true")
                
                lines.append("tasks:")
                # tasks
                tasks_yaml = to_yaml_list(level['tasks'], indent=2)
                content = '\n'.join(lines) + '\n' + tasks_yaml + '\n\n'
                write_text(os.path.join(item_dir, '_data.yaml'), content)
                
                # Copy icon if available
                if icons_dir:
                    copy_icon(icons_dir, group_id, item_id, item_dir)


# --- Main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dart', required=True, help='Path to Dart file with SprawBookData')
    ap.add_argument('--out', required=True, help='Output directory (e.g., assets/sprawnosci/zhp_harc_sim_2022)')
    ap.add_argument('--icons', help='Optional path to icons directory (e.g., lib/sprawnosci/tmp/zhp_harc_sim_2022)')
    args = ap.parse_args()

    with open(args.dart, 'r', encoding='utf-8') as f:
        dart_text = f.read()

    book = parse_spraw_book(dart_text)

    # If output directory name provides a better id, use that for book id in _data.yaml
    out_basename = os.path.basename(os.path.normpath(args.out))
    if out_basename:
        book['id'] = out_basename

    emit_assets(book, args.out, args.icons)
    print(f"Done. Wrote assets to {args.out}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
