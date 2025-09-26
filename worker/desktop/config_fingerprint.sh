#!/bin/bash

ID=$1
WORKDIR=/opt/tg_clients/clients/client_$ID

# Создание WINEPREFIX
export WINEPREFIX=$WORKDIR/wine_env
wineboot -u

# Настройка "устройства"
wine reg add "HKCU\\Software\\Wine\\Wine\\Explorer" /v Desktop /t REG_SZ /d "1920x1080" /f
wine reg add "HKCU\\Software\\Wine\\Drivers" /v Video /t REG_SZ /d "NVIDIA GeForce RTX 4090" /f

# Подмена информации
wine reg add "HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion" /v ProductName /t REG_SZ /d "Windows 11 Pro" /f
wine reg add "HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion" /v CurrentBuild /t REG_SZ /d "22621" /f
