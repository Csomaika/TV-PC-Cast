# TV-PC Cast

Magyar nyelvű képernyőtükrözés Windows 10/11 (x64) rendszeren. A **Közvetlen böngészős mód** a helyi hálózaton továbbítja a számítógép képét és rendszerhangját a TV böngészőjébe WebRTC-vel, ha a fogadó böngésző támogatja. Az MJPEG/JPEG tartalék mód hang nélküli képet ad. A **Vezeték nélküli kijelző** lapon külön elérhető a Windows Miracast-kapcsolata.

## Telepítés

1. Töltsd le és indítsd el a **TVPCCast-Setup.exe** fájlt. A kiadásokhoz a telepítő mellett a **SHA256SUMS.txt** ellenőrzőösszeg-fájl is elérhető. [GitHub Releases](../../releases)
2. Alapértelmezés szerint a telepítő az aktuális felhasználónak telepít, rendszergazdai jog nélkül. A Start menüben létrejön a **TV-PC Cast** parancsikon. Az asztali parancsikon alapból be van jelölve.
3. Eltávolításhoz válaszd a **TV-PC Cast** elemet a Windows Gépház alkalmazáslistájában.

A telepítés nélküli változathoz bontsd ki a teljes **TVPCCast-Portable.zip** csomagot. A kibontott `TVPCCast` mappában indítsd el a `TVPCCast.exe` fájlt. Az alkalmazás a mellette lévő `_internal` mappából tölti be a függőségeit.

## Közvetlen kép- és hangátvitel a TV böngészőjében

1. Csatlakoztasd a PC-t és a TV-t ugyanahhoz az otthoni hálózathoz. Az útválasztónak engednie kell az egymás közti kommunikációt.
2. A **Közvetlen böngészős mód** lapon válassz egy monitort vagy az összes monitor közös asztalát. A képméret felső határa 720p, 1080p, 1440p vagy 4K lehet. A képkockasebesség célértéke 6, 10, 15, 24 vagy 30 FPS. A program megtartja a képarányt, a tényleges sebesség a PC-től, a hálózattól és a TV böngészőjétől függ.
3. Kattints a **Közvetítés indítása** gombra. A TV böngészőjében nyisd meg a PC-n megjelenő teljes címet, például `http://192.168.1.23:8765`, majd írd be a hatjegyű PIN-kódot.
4. A TV távirányítójával válaszd a **Kép és hang (WebRTC)** gombot. A böngésző némítva indítja a videót, utána a **Hang bekapcsolása** gombbal kapcsolhatod be a hangot. Ha ezt a böngésző külön kéri, válaszd a **Lejátszás és hang bekapcsolása** gombot.
5. Indítsd el a videót a PC-n a KMPlayerben, és töltsd be a magyar SRT-t. A TV-n a kiválasztott Windows-kijelző képe jelenik meg, a rajta látható felirattal együtt. A program a Windows alapértelmezett hangkimenetének jelét rögzíti, ezért a lejátszóban is ezt a kimenetet válaszd.
6. A TV-n a **Bontás** gombbal léphetsz ki a nézetből. A PC-n a **Közvetítés leállítása** leállítja a helyi közvetítést.

A WebRTC mód kísérleti, a 65E8S Odin böngészőjében a kép és hang működését még ellenőrizni kell. Ha a böngésző nem tud WebRTC-n csatlakozni, az oldal visszatér a csak kép módhoz és megjeleníti az okot. A csak kép mód először MJPEG-et próbál. Ha az első kép nem jelenik meg, automatikusan egyesével frissülő JPEG-képekre vált. A **JPEG mód** gombbal kézzel is válthatsz.

A WebRTC hang- és képforgalma titkosított. A JPEG-képek, a párosítás és a WebRTC kapcsolatindítás adatai titkosítatlan helyi HTTP-n mennek. Használd megbízható otthoni hálózaton. A minden felhasználóra telepített változat a programhoz kötött TCP/8765-ös bejövő szabályt hoz létre a Windows privát hálózati profilján a helyi alhálózathoz. Az aktuális felhasználós és a telepítés nélküli változatnál a Windows tűzfala külön engedélyt kérhet a privát hálózatra.

## Hisense 65E8S csatlakoztatása Miracasttal

1. Kapcsold be a PC Wi-Fi-jét. A TV-n válaszd a **Képernyőmegosztás / Screen Sharing** bemenetet vagy a **Cast** néven megjelenő kivetítési módot.
2. A TV-PC Cast **Vezeték nélküli kijelző** lapján kattints a **TV keresése / leválasztása** gombra. A Windows paneljén válaszd ki a tévét, és szükség esetén hagyd jóvá a csatlakozást a TV-n. A panelt közvetlenül a **Win + K** billentyűkkel is megnyithatod.
3. A **Kivetítés módja** gombbal (**Win + P**) válaszd a **Megkettőzés** lehetőséget tükrözéshez, vagy a **Kiterjesztés** lehetőséget ahhoz, hogy a TV külön kijelzőként működjön.
4. Ha a videó hangja a PC-n marad, a **Hangbeállítások** gombbal nyisd meg a Windows hangkimeneteit. Ha a TV szerepel a listában, állítsd be kimenetnek. A KMPlayerben válaszd a rendszer alapértelmezett kimenetét, ha a lejátszóban korábban külön eszközt állítottál be.
5. Kikapcsoláshoz nyisd meg újra a Windows **Win + K** paneljét és válaszd a **Leválasztás** lehetőséget. A Windows itt mutatja a natív kapcsolat állapotát.

A KMPlayerben betöltött magyar SRT a videó képével együtt jelenhet meg, ha a lejátszó megjeleníti a feliratot a kivetített kijelzőn. Az alkalmazásnak ehhez nem kell megnyitnia a feliratfájlt. A Windows állapítja meg az elérhető megjelenítési módokat, és a PC, a meghajtók, a rádiós kapcsolat és a TV együtt határozza meg a tényleges felbontást, képkockasebességet és a hang–kép késését. Az adott 65E8S készüléken az **1080p/60 FPS**, a **4K**, a hang és a szinkron külön helyszíni ellenőrzést igényel. [Microsoft útmutató a vezeték nélküli kijelzőhöz](https://support.microsoft.com/hu-hu/windows/hardware/display-graphics/screen-mirroring-and-projecting-to-your-pc-or-wireless-display)

## Eszközkeresés a helyi hálózaton

A **Hálózati eszközök** lapon az **Eszközök keresése** a kiválasztott hálózati címen megjeleníti a UPnP/SSDP keresésre válaszoló eszközöket, és megjelöli a hálózati médialejátszókat. A **Közvetlen böngészős módhoz** a TV-n a PC címét kell megnyitni. A Miracast eszközlistáját a **Win + K** panel mutatja. A TV akkor is megjelenhet a Windows paneljén, ha a UPnP/SSDP keresésre nem válaszol.

## A 65E8S csatlakozási lehetőségei

| Mód | Mire használható ezen a projekten belül |
| --- | --- |
| **Windows Miracast / Hisense Screen Sharing** | A Hisense magyar adatlapja igazolja a Screen Sharing funkciót a 20018824 cikkszámú, 6942351434773 EAN-kódú VIDAA modellen. Az azonos EAN-kódú spanyol adatlap Anyview Cast / Screen Sharing néven jelöli, az európai U9 kézikönyv pedig Windows PC-hez Miracastot ír elő. A Windows intézi az eszközkeresést, az asztal tükrözését és a kompatibilis hangkimenetet. A Windows Miracast hardveresen gyorsított H.264 kódolást használ, a H.265 és a nagyobb felbontás hardverfüggő. [Hisense Magyarország](https://hu.hisense.com/termekek/televizio/uled-miniled-tv/TV-SET-65E8S-HSN/p/000000000020018824) · [Hisense Spanyolország](https://www.hisense.es/televisores/miniled/serie-e8-miniled-tv-hisense-65e8s/) · [Hisense európai VIDAA U9 kézikönyv](https://www.hisense.com.my/wp-content/uploads/2025/08/93041_9603VIDAA_U9_EUEMCO_E-Manual_eng_202502%E5%AE%8C%E6%95%B4%E6%9F%A5%E7%9C%8B%E7%89%88.pdf) · [Microsoft hardverkövetelmények](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/wireless-projection-pc-manufacturers) |
| **Böngésző, MJPEG / JPEG** | Képtükrözés közös helyi hálózaton. Az azonos EAN-kódú modell spanyol adatlapja Odin böngészőt tüntet fel. A konkrét TV firmware-jén a JPEG és MJPEG működése külön ellenőrizendő. [Hisense Spanyolország](https://www.hisense.es/televisores/miniled/serie-e8-miniled-tv-hisense-65e8s/) |
| **WebRTC** | Kísérleti helyi kép- és hangátvitel. A PC szoftveres videókódolást és a Windows alapértelmezett kimenetének WASAPI-hangrögzítését használja. A VIDAA webalkalmazás-fejlesztői útmutató szoftveres WebRTC-dekódolást sorol fel. A 65E8S Odin böngészőjének WebRTC- és kodektámogatása nincs igazolva. [VIDAA fejlesztői útmutató](https://www.vidaa.com/wp-content/uploads/2020/12/WebApp_Development_Guide_for_VIDAA.pdf) |
| **DLNA / DMP–DMR** | A magyar termékadatlap médiafájlok hálózati lejátszására szolgáló DMP/DMR funkciót jelez. Élő Windows-asztalhoz és a KMPlayerben megjelenített felirathoz a Miracast a dokumentált út. [Hisense Magyarország](https://hu.hisense.com/termekek/televizio/uled-miniled-tv/TV-SET-65E8S-HSN/p/000000000020018824) · [Microsoft DLNA-áttekintés](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-dlnhnd/d40517ad-2d0a-4397-a46b-db7ba281a837) |
| **AirPlay 2** | A magyar adatlap igazolja a TV AirPlay 2 támogatását. A TV-PC Cast Windowsról a Miracast és a böngészős útvonalat kínálja. [Hisense Magyarország](https://hu.hisense.com/termekek/televizio/uled-miniled-tv/TV-SET-65E8S-HSN/p/000000000020018824) |

## Hibaelhárítás

- **Nem indul az EXE.** A vizsgált gépen a Panda Dome karanténba tette a 0.1.0-s, egyfájlos és kódaláírás nélküli `TVPCCast.exe`-t. Az új csomag külön mappában tartja a függőségeket, így induláskor nincs ideiglenes önkibontás. A csomag továbbra is kódaláírás nélküli, ezért a vírusirtók döntése a helyi védelemtől függ. Ellenőrizd a letöltés SHA-256 értékét a kiadásban szereplő ellenőrzőösszeghez képest (`Get-FileHash .\TVPCCast-Setup.exe -Algorithm SHA256`). Telepítés nélküli futtatásnál bontsd ki az egész ZIP-et. Újabb blokkolásnál keresd meg a futtatás időpontjához tartozó eseményt a vírusirtó karanténnaplójában vagy a **Windows biztonság → Védelmi előzmények** felületen. Ha az alkalmazás eljut a Python indításáig, az alkalmazáshibák naplója a `%LOCALAPPDATA%\TV-PC Cast\startup.log` útvonalon található. [Microsoft útmutató a védelmi előzményekhez](https://support.microsoft.com/en-us/windows/security/windows-security/protection-history-in-the-windows-security-app) · [Smart App Control és digitális aláírás](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions)
- **A Windows nem találja a TV-t.** Ellenőrizd a TV **Képernyőmegosztás** bemenetét, a Wi-Fi-t, a PC Miracast-képességét és a hálózati, illetve grafikus illesztőprogramokat. A **Win + K** panel jelzi, ha a gépen a vezeték nélküli kivetítés nem érhető el. [Microsoft hibaelhárítás](https://support.microsoft.com/en-us/windows/hardware/display-graphics/fix-connections-to-wireless-displays-or-docks-in-windows)
- **A böngésző nem éri el a címet.** A PC-n a tényleges otthoni hálózathoz tartozó címet válaszd. Ellenőrizd a Windows privát hálózati profilját, a TCP/8765 elérhetőségét és a router vendéghálózati vagy klienselkülönítési beállítását.
- **WebRTC-kép van, hang nincs.** A TV-n válaszd a **Hang bekapcsolása** gombot, és ellenőrizd, hogy a PC lejátszója a Windows alapértelmezett hangkimenetét használja. Ha a kimenetet megváltoztatod, indítsd újra a közvetítést.
- **A böngészős kép akadozik.** Kezdetnek válaszd a 720p / 10 FPS beállítást egy monitorral. Ellenőrizd a kiválasztott kijelzőt és a PC munkamenetét, ha fekete kép jelenik meg. Egyes védett tartalmak fekete képként jelenhetnek meg.

## Ellenőrzés és fejlesztői futtatás

A Windows kiadási folyamat ellenőrzi a kibontott és a telepített alkalmazás grafikus indítását, a helyi képrögzítést és a PIN-kódos kiszolgálást, továbbá az indítást normál módban, a parancsikonokat és az eltávolítást. Ezek a lépések a helyi Windows 10 teszten 1920×1080-as rögzített képpel teljesültek. Windows 10-en, Chrome-ban, a PC Wi-Fi-címén WebRTC-n 1920×1080 felbontású élő kép és hangcsomagok érkeztek, és a kézi némításfeloldás működött. Ugyanott az MJPEG, a JPEG és az automatikus JPEG-váltás is működött. A Hisense 65E8S tévén a tükrözés, a magyar felirat megjelenése, a hangszinkron, az elért felbontás és a tartós lejátszás együttes ellenőrzése még hátravan.

Futtatás és tesztek Windows alatt, Python 3.12-vel

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest pyinstaller
.\.venv\Scripts\python.exe tvpc_cast.py
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/viewer.test.cjs
```

Helyi csomagolás Inno Setup 6-tal, külön tesztfiókban vagy olyan Windows-környezetben, ahol még nincs telepítve a TV-PC Cast

```powershell
.\scripts\build-windows.ps1 -Python .\.venv\Scripts\python.exe
.\scripts\test-windows-install.ps1
```

A [Windows GitHub Actions folyamat](../../actions/workflows/windows-build.yml) futásából letölthető a tesztelt csomag. A `v*` verziótagok futása a telepítőt, a telepítés nélküli ZIP-et és az ellenőrzőösszeg-fájlt a [GitHub Releases](../../releases) oldalra tölti fel.

## Licenc

[MIT](LICENSE)
