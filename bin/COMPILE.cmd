@echo off

:: This is an example compiler script

SET PYTHON64=c:\python312-64\python.exe
SET PYTHON32=c:\python37-32\python.exe


cd C:\GIT\npbackup
git pull || GOTO ERROR

:: cd RESTIC_SOURCE_FILES
:: cat update_restic.sh | dos2unix | sh
:: cd ..

:: Make sure we add npbackup in python path so bin and npbackup subfolders become packages
SET OLD_PYTHONPATH=%PYTHONPATH%
SET PYTHONPATH=c:\GIT\npbackup

%PYTHON64% RESTIC_SOURCE_FILES/update_restic.py || GOTO ERROR

%PYTHON64% -m pip install pytest
%PYTHON64% -m pytest /opt/npbackup/tests || GOTO ERROR

"%PYTHON64%" -m pip install --upgrade -r npbackup/requirements.txt || GOTO ERROR
"%PYTHON64%" bin\compile.py --audience all --sign "C:\ODJ\KEYS\NetInventEV.dat"


"%PYTHON32%" -m pip install --upgrade -r npbackup/requirements.txt || GOTO ERROR
"%PYTHON32%" bin\compile.py --audience all --sign "C:\ODJ\KEYS\NetInventEV.dat"

:ERROR
echo "Failed to run build script"
:END
SET PYTHONPATH=%OLD_PYTHONPATH%



