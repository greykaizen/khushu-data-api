#!/usr/bin/env python3
"""Build assets/adhan/adhan_index.json — catalog the 178 donor adhan opus
files with reciter/region/style parsed from filenames, sample rate + sha256
from the files. Audio stays byte-identical (no re-encode). Run from repo root.
"""
import os, re, json, struct, hashlib

ADHAN_DIR = 'assets/adhan'

REGIONS = {
    'messr': 'Misr (Egypt)', 'mesr': 'Misr (Egypt)', 'al_qahera': 'Cairo, Misr',
    'lubnan': 'Lebanon', 'al_kuwait': 'Kuwait', 'qatar': 'Qatar',
    'al_saudea': 'Saudi Arabia', 'al_saoudea': 'Saudi Arabia', 'saudia': 'Saudi Arabia', 'saudya': 'Saudi Arabia',
    'turkia': 'Turkey', 'al_jazaer': 'Algeria', 'jazaer': 'Algeria', 'al_jazaire': 'Algeria',
    'felesteen': 'Palestine', 'al_quds': 'Al-Quds', 'quds': 'Al-Quds',
    'al_urdun': 'Jordan', 'afganistan': 'Afghanistan', 'al_maghreb': 'Morocco',
    'al_iraq': 'Iraq', 'colombia': 'Colombia', 'al_riad': 'Riyadh', 'najran': 'Najran',
}
PLACES = {
    'al_haram_al_maqe': 'Haram, Makkah', 'al_haram_al_make': 'Haram, Makkah',
    'al_haram_al_madade': 'Haram, Madinah', 'al_haram_al_madane': 'Haram, Madinah',
    'al_madena_al_nabawya': "Prophet's Mosque, Madinah", 'al_madena_al_nabaweya': "Prophet's Mosque, Madinah",
    'masjed_al_aqssa': 'Al-Aqsa Mosque', 'al_massjid_al_aqsa': 'Al-Aqsa Mosque',
    'masjed_al_refae': 'Al-Refai Mosque, Cairo', 'al_muqarama': 'Makkah',
    'muqarama': 'Makkah',
    'jamee_al_emam_muhammad_bnu_abd_al_wahab_al_dafna': 'Imam Muhammad ibn Abd al-Wahhab Mosque, Dafna',
    'jamee_al_imam_muhammad_bnu_abd_al_wahab_al_dafna': 'Imam Muhammad ibn Abd al-Wahhab Mosque, Dafna',
    'jamee_al_rajehe': "Jami' al-Rajahi", 'jamee_al_malek_fahd': 'King Fahd Mosque',
    'omar_bnu_al_khatab': 'Omar bin al-Khattab Mosque',
}
STYLES = {'al_fajr': 'Fajr', 'fajr': 'Fajr', 'al_maghreb': 'Maghrib'}


def opus_meta(path):
    with open(path, 'rb') as f:
        head = f.read(512)
    if not head.startswith(b'O'):
        return None
    i = head.find(b'OpusHead')
    if i < 0:
        return None
    ch = head[i + 9]
    rate = struct.unpack('<i', head[i + 12:i + 16])[0]
    return ch, rate


def find_first(s, table):
    for k, v in table.items():
        if k in s:
            return v
    return None


def parse_name(stem):
    """Return (reciter, region, style)."""
    # Place-led adhans (no reciter): 'adhan_al_haram_...', 'adhan_masjed_...'
    place = find_first(stem, PLACES)
    region = find_first(stem, REGIONS)
    style = None
    for k, v in STYLES.items():
        if k in stem and not (k == 'al_maghreb'):
            style = v
            break
    if stem.startswith('adhan_') or stem.startswith('adhan_') or stem.split('_')[0] == 'adhan':
        label = 'Adhan — ' + (place or region or 'Unknown place')
        return label, region or place, style or ('Eid Takbir' if 'takberat' in stem else None)
    # Reciter-led: everything before 'adhan'/'adan' keyword is the reciter
    parts = re.split(r'_adhan_|_adan_', stem)
    reciter = parts[0].replace('_', ' ').title().strip()
    rest = parts[1] if len(parts) > 1 else ''
    if place and place not in (region,):
        region = region or place
    if 'takberat' in stem or 'taqberat' in stem:
        style = 'Eid Takbir'
    return reciter, region or place, style


def main():
    entries = []
    for fn in sorted(os.listdir(ADHAN_DIR)):
        if not fn.endswith('.opus'):
            continue
        stem = fn[:-5]
        hm = re.search(r'^(.*)_[0-9a-f]{12}$', stem)
        base = hm.group(1) if hm else stem
        reciter, region, style = parse_name(base)
        path = os.path.join(ADHAN_DIR, fn)
        size = os.path.getsize(path)
        meta = opus_meta(path)
        with open(path, 'rb') as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        entries.append({
            'id': base,
            'reciter': reciter,
            'region': region,
            'style': style,
            'file': f'assets/adhan/{fn}',
            'format': 'opus',
            'sampleRateHz': meta[1] if meta else None,
            'channels': meta[0] if meta else None,
            'sizeBytes': size,
            'sha256': sha,
        })
    out = {
        '_meta': {
            'exported_at': '2026-08-31',
            'source': 'assets/adhan/*.opus (donor-collected adhan recordings; per-reciter permissions in LICENSE-CONTENT.md)',
            'count': len(entries),
            'extractor': 'tools/build_adhan_index.py',
            'note': 'ids are hash-stripped filename stems; audio stays byte-identical to donors (no re-encode)',
        },
        'entries': entries,
    }
    with open(os.path.join(ADHAN_DIR, 'adhan_index.json'), 'w') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print('entries:', len(entries))
    reciters = sorted({e['reciter'] for e in entries})
    print('distinct reciters:', len(reciters))
    no_region = [e for e in entries if not e['region']]
    print('entries without region:', len(no_region))
    styles = {}
    for e in entries:
        styles[e['style'] or 'standard'] = styles.get(e['style'] or 'standard', 0) + 1
    print('styles:', styles)


if __name__ == '__main__':
    main()
