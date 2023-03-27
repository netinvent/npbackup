@echo off

:: This is an example compiler script

SET PYTHON64=c:\python310-64\python.exe
SET PYTHON32=c:\python37-32\python.exe


cd C:\GIT\npbackup

:: Make sure we add npbackup in python path so bin and npbackup subfolders become packages
SET PYTHONPATH=c:\GIT\npbackup

"%PYTHON64%" bin\compile.py --audience all
"%PYTHON32%" bin\compile.py --audience all



