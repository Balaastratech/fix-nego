#!/bin/bash
# Complete dependency fix for k2 + pyannote + wespeaker
# This installs torch 2.1.0 which is the ONLY version compatible with all packages

echo "=== Step 1: Uninstalling conflicting packages ==="
pip uninstall -y k2 torch torchaudio pyannote-audio wespeaker hdbscan speechbrain pytorch-lightning lightning

echo "=== Step 2: Installing torch 2.1.0 (required for k2 compatibility) ==="
pip install torch==2.1.0 torchaudio==2.1.0

echo "=== Step 3: Installing k2 for torch 2.1.0 ==="
pip install k2==1.24.4.dev20240223+cpu.torch2.1.0 -f https://k2-fsa.github.io/k2/cpu.html

echo "=== Step 4: Installing pyannote-audio 3.1.1 (compatible with torch 2.1.0) ==="
# pyannote 4.x requires torch>=2.8, but 3.1.1 works with torch 2.1
pip install pyannote-audio==3.1.1

echo "=== Step 5: Installing correct hdbscan for wespeaker ==="
pip install hdbscan==0.8.37

echo "=== Step 6: Installing wespeaker ==="
pip install wespeaker

echo "=== Step 7: Installing speechbrain and lightning (compatible with torch 2.1) ==="
pip install speechbrain==1.1.0
pip install pytorch-lightning==2.1.0 lightning==2.1.0

echo "=== Step 8: Installing missing webrtcvad ==="
pip install webrtcvad>=2.0.10

echo "=== Step 9: Reinstalling other requirements (without overwriting torch) ==="
pip install --no-deps -r requirements.txt

echo "=== Step 10: Verification ==="
python -c "import k2; print('✓ k2 imported')"
python -c "import pyannote.audio; print('✓ pyannote.audio imported')"
python -c "import wespeaker; print('✓ wespeaker imported')"
python -c "import torch; print(f'✓ torch {torch.__version__}')"
python -c "import speechbrain; print('✓ speechbrain imported')"

echo ""
echo "=== Installation Complete ==="
echo "torch version: 2.1.0"
echo "pyannote.audio version: 3.1.1"
echo "k2 version: 1.24.4.dev20240223+cpu.torch2.1.0"
