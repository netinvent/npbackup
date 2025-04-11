@echo off

:: This is an example compiler script

SET PYTHON64=c:\python313-64\python.exe
SET PYTHON64-LEGACY=c:\python38-64\python.exe
SET PYTHON32=c:\python313-32\python.exe
SET PYTHON32-LEGACY=c:\python38-32\python.exe


cd C:\GIT\npbackup
git pull || GOTO ERROR

:: Make sure we add npbackup in python path so bin and npbackup subfolders become packages
SET OLD_PYTHONPATH=%PYTHONPATH%
SET PYTHONPATH=c:\GIT\npbackup

"%PYTHON64%" RESTIC_SOURCE_FILES/update_restic.py || GOTO ERROR

:: BUILD 64-BIT VERSION
"%PYTHON64%" -m pip install --upgrade pip || GOTO ERROR
"%PYTHON64%" -m pip install pytest
"%PYTHON64%" -m pip install --upgrade -r npbackup/requirements.txt || GOTO ERROR

"%PYTHON64%" -m pytest C:\GIT\npbackup\tests || GOTO ERROR

"%PYTHON64%" bin\compile.py --sign "C:\ODJ\KEYS\NetInventEV.dat" %*

:: BUILD 64-BIT LEGACY VERSION
"%PYTHON64-LEGACY%" -m pip install --upgrade pip || GOTO ERROR
"%PYTHON64-LEGACY%" -m pip install pytest
"%PYTHON64-LEGACY%" -m pip install --upgrade -r npbackup/requirements.txt || GOTO ERROR

"%PYTHON64-LEGACY%" -m pytest C:\GIT\npbackup\tests || GOTO ERROR

"%PYTHON64-LEGACY%" bin\compile.py --sign "C:\ODJ\KEYS\NetInventEV.dat" %*

:: BUILD 32-BIT VERSION
"%PYTHON32%" -m pip install --upgrade pip || GOTO ERROR
"%PYTHON32%" -m pip install pytest
"%PYTHON32%" -m pip install --upgrade -r npbackup/requirements-win32.txt || GOTO ERROR

"%PYTHON32%" -m pytest C:\GIT\npbackup\tests || GOTO ERROR

"%PYTHON32%" bin\compile.py --sign "C:\ODJ\KEYS\NetInventEV.dat" %*

"%PYTHON64%" RESTIC_SOURCE_FILES/update_restic.py || GOTO ERROR

:: BUILD 32-BIT LEGACY VERSION
"%PYTHON32-LEGACY%" -m pip install --upgrade pip || GOTO ERROR
"%PYTHON32-LEGACY%" -m pip install pytest
"%PYTHON32-LEGACY%" -m pip install --upgrade -r npbackup/requirements.txt || GOTO ERROR

"%PYTHON32-LEGACY%" -m pytest C:\GIT\npbackup\tests || GOTO ERROR

"%PYTHON32-LEGACY%" bin\compile.py --sign "C:\ODJ\KEYS\NetInventEV.dat" %*
GOTO END

:ERROR
echo "Failed to run build script"
:END
SET PYTHONPATH=%OLD_PYTHONPATH%



