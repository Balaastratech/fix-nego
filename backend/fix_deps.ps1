# PowerShell script to fix k2 dependencies
# Run with: .\fix_deps.ps1

Write-Host "=== Uninstalling conflicting packages ===" -ForegroundColor Yellow
pip uninstall -y k2 pyannote-audio hdbscan speechbrain pytorch-lightning lightning

Write-Host "`n=== Installing pyannote-audio 3.1.1 (compatible with torch 2.1) ===" -ForegroundColor Yellow
pip install pyannote-audio==3.1.1

Write-Host "`n=== Installing correct hdbscan for wespeaker ===" -ForegroundColor Yellow
pip install hdbscan==0.8.37

Write-Host "`n=== Installing speechbrain and lightning (compatible with torch 2.1) ===" -ForegroundColor Yellow
pip install speechbrain==1.1.0
pip install pytorch-lightning==2.1.0 lightning==2.1.0

Write-Host "`n=== Installing missing webrtcvad ===" -ForegroundColor Yellow
pip install webrtcvad>=2.0.10

Write-Host "`n=== Verification ===" -ForegroundColor Green
python -c "import k2; print('✓ k2 imported')"
python -c "import pyannote.audio; print('✓ pyannote.audio imported')"
python -c "import wespeaker; print('✓ wespeaker imported')"
python -c "import torch; print(f'✓ torch {torch.__version__}')"
python -c "import speechbrain; print('✓ speechbrain imported')"

Write-Host "`n=== Done ===" -ForegroundColor Green
