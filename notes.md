## 1. Converter

### Local build
cd converter
python3 convert_forum.py
python3 convert_forum.py html-only

### Run site locally
cd build/static_archive
python3 -m http.server 7000

### Build and deploy
./scripts/deploy.sh
./scripts/deploy.sh html-only


## 2. DM Converter

cd dm-converter
python3 convert_dms.py [userID]
python3 convert_dms.py 49