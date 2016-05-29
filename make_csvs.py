#!/usr/bin/env python3

import collections
import csv
import pathlib
import re
import shutil
import tempfile
import ck2parser
from ck2parser import rootpath
import print_time

def process_provinces(parser, default_tree):
    id_name_map = {}
    defs_path = parser.file('map/' + default_tree['definitions'].val)
    for row in ck2parser.csv_rows(defs_path):
        try:
            id_name_map[row[0]] = row[4]
        except IndexError:
            continue
    prov_title = {}
    for path in parser.files('history/provinces/* - *.txt'):
        number, name = path.stem.split(' - ')
        if id_name_map.get(number) == name:
            the_id = 'PROV{}'.format(number)
            tree = parser.parse_file(path)
            try:
                prov_title[the_id] = tree['title'].val
            except KeyError:
                pass
    return prov_title

def process_regions(parser, default_tree):
    title_region = {}
    path = parser.file('map/' + default_tree['geographical_region'].val)
    tree = parser.parse_file(path)
    for n, v in tree:
        if n.val.startswith('world_') and 'regions' not in v.dictionary:
            assert len(v) == 1
            region = n.val[6:]
            try:
                for x in v['duchies']:
                    title_region[x.val] = region
            except KeyError:
                print(n.val)
                raise
    return title_region

def process_landed_titles(parser, lt_keys, title_region):
    def recurse(tree, liege_region=None):
        for n, v in tree:
            if ck2parser.is_codename(n.val):
                attrs = []
                for n2, v2 in v:
                    if n2.val in lt_keys:
                        try:
                            value = v2.val
                        except AttributeError:
                            value = ' '.join(s.val for s in v2)
                        attrs.append((n2.val, value))
                title_attrs[n.val] = attrs
                if n.val[0] in 'cb':
                    title_region[n.val] = liege_region
                if n.val[0] in 'dc':
                    for _ in recurse(v, title_region.get(n.val)):
                        pass
                if n.val[0] in 'ek':
                    try:
                        title_region[n.val] = collections.Counter(
                            recurse(v)).most_common()[0][0]
                    except IndexError:
                        pass
                yield title_region.get(n.val)
    title_attrs = collections.OrderedDict()
    for _, tree in parser.parse_files('common/landed_titles/*'):
        for _ in recurse(tree):
            pass
    return title_attrs

def process_localisation(parser, title_attrs, prov_title):
    other_locs = collections.OrderedDict()
    seen = set()
    for path in parser.files('localisation/*', reverse=True):
        for row in ck2parser.csv_rows(path):
            key, value = row[0:2]
            if key not in seen:
                seen.add(key)
                if re.match('[ekdcb]_', key):
                    adj_match = re.match('(.+)_adj(_|$)', key)
                    title = key if not adj_match else adj_match.group(1) 
                elif re.match('PROV\d+', key):
                    if key in prov_title:
                        title = prov_title[key]
                    else:
                        other_locs[key] = value
                        continue
                else:
                    continue
                try:
                    title_attrs[title].append((key, value))
                except KeyError:
                    pass
    return other_locs

def sort_attrs(attrs, lt_keys, cultures):
    for pairs in attrs.values():
        pairs.sort(key=lambda x: (x[0] in cultures, x[0] in lt_keys, x))

def read_prev():
    prev_title_attrs = collections.defaultdict(dict)
    prev_other_locs = {}
    for path in ck2parser.files('*.csv', basedir=(rootpath / 'SLD/templates')):
        with path.open(encoding='cp1252', newline='') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)
            if 'other_provinces' in path.name:
                for row in reader:
                    key, value = row[:2]
                    prev_other_locs[key] = value
            else:
                for row in reader:
                    title, key, value = row[:3]
                    prev_title_attrs[title][key] = value
    return prev_title_attrs, prev_other_locs

def write_output(title_attrs, title_region, other_locs, prev_title_attrs,
                 prev_other_locs):
    out_row_lists = collections.defaultdict(
        lambda: ['#TITLE;KEY;VALUE;SWMH;;;;;;;;;;;x'.split(';')])
    for title, pairs in title_attrs.items():
        out_rows = out_row_lists[title_region.get(title)]
        for key, value in pairs:
            try:
                prev = prev_title_attrs[title][key]
            except KeyError:
                prev = ''
            out_rows.append([title, key, prev, value] + [''] * 10 + ['x'])
    with tempfile.TemporaryDirectory() as td:
        templates_t = pathlib.Path(td)
        for region, out_rows in out_row_lists.items():
            region = region if region else 'titular'
            out_path = templates_t / 'zz~_SLD_{}.csv'.format(region)
            with out_path.open('w', encoding='cp1252', newline='') as csvfile:
                csv.writer(csvfile).writerows(out_rows)
        out_path = templates_t / 'zz~_SLD_other_provinces.csv'
        out_rows = ['#KEY;VALUE;SWMH;;;;;;;;;;;;x'.split(';')]
        for key, value in sorted(other_locs.items(),
                                 key=lambda x: int(x[0][4:])):
            prev = prev_other_locs.get(key, '')
            out_rows.append([key, prev, value] + [''] * 11 + ['x'])
        with out_path.open('w', encoding='cp1252', newline='') as csvfile:
            csv.writer(csvfile).writerows(out_rows)
        templates = rootpath / 'SLD/templates'
        shutil.rmtree(str(templates))
        shutil.copytree(str(templates_t), str(templates))

@print_time.print_time
def main():
    parser = ck2parser.SimpleParser(rootpath / 'SWMH-BETA/SWMH')
    default_tree = parser.parse_file(parser.file('map/default.map'))
    prov_title = process_provinces(parser, default_tree)
    title_region = process_regions(parser, default_tree)
    lt_keys = {'title', 'title_female', 'foa', 'title_prefix', 'short_name',
        'name_tier', 'location_ruler_title', 'dynasty_title_names',
        'male_names'}
    cultures = set(ck2parser.get_cultures(parser, groups=False))
    title_attrs = process_landed_titles(parser, lt_keys | cultures,
                                        title_region)
    other_locs = process_localisation(parser, title_attrs, prov_title)
    sort_attrs(title_attrs, lt_keys, cultures)
    prev_title_attrs, prev_other_locs = read_prev()
    write_output(title_attrs, title_region, other_locs, prev_title_attrs,
                 prev_other_locs)

if __name__ == '__main__':
    main()
