# Ravenswatch RE Tools

> **DEPRECATED — Do not use.** See `rw/docs/` for current documentation. This file is pending cleanup and may contain stale or incorrect information.


## Save File Tools

### mod_save.py
Modify save values by GUID or offset.

```bash
# Show known values
python scripts/python/rw/mod_save.py Profile_1.ob --show

# Set Level to 15
python scripts/python/rw/mod_save.py Profile_1.ob --set Level 15 -o modded.ob
```

Location: `scripts/python/rw/mod_save.py`

### analyze_save.py
Find record markers, extract strings, search for values.

Location: `scripts/python/rw/analyze_save.py`

## Cipher Tools

### decode-name-cypher-fixed.js
Decode ciphered asset filenames. Working for all common cases.

```bash
# Decode a single name
node -e "const {decypher} = require('./interim/decode-name-cypher-fixed.js'); console.log(decypher('Kqjjqiir'))"
# Output: Geppetto

# Decode tree.txt (only content inside _Cooking is ciphered)
node -e "
const {decypher} = require('./decode-name-cypher-fixed.js');
const fs = require('fs');
const lines = fs.readFileSync('tree.txt', 'utf8').split('\n');
let inCooking = false;
const decoded = lines.map(line => {
  if (line.includes('+---_Cooking')) { inCooking = true; return line; }
  return inCooking ? decypher(line) : line;
});
fs.writeFileSync('tree-decoded.txt', decoded.join('\n'));
"
```

Location: `interim/decode-name-cypher-fixed.js`

**Note:** Root level files (ApplicationSettings.ot, etc.) are plaintext. Only content inside `_Cooking/` folder is ciphered.

## Other

### checksum_probe_click.py
CRC32 checksum probe tool.

Location: `interim/checksum_probe_click.py`

## Decoded Outputs

- `interim/dumps/UsedRscList-decoded.ot` - decoded asset list
- `interim/tree-decoded.txt` - decoded directory tree
