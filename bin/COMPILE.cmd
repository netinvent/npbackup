@echo off

:: This is an example compiler script

SET PYTHON64=c:\python312-64\python.exe
SET PYTHON32=c:\python37-32\python.exe


cd C:\GIT\npbackup
git pull || exit 1

:: Make sure we add npbackup in python path so bin and npbackup subfolders become packages
SET OLD_PYTHONPATH=%PYTHONPATH%
SET PYTHONPATH=c:\GIT\npbackup

"%PYTHON64%" -m pip install --upgrade -r npbackup/requirements.txt || exit 1
"%PYTHON64%" bin\compile.py --audience all

"%PYTHON32%" -m pip install --upgrade -r npbackup/requirements.txt || exit 1
"%PYTHON32%" bin\compile.py --audience all

SET PYTHONPATH=%OLD_PYTHONPATH%



