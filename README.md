# TV-PC Cast 📺

Windows 10/11 képernyőtükrözés Smart TV-re a helyi Wi-Fi/LAN hálózaton. Elsősorban **Hisense VIDAA** televíziókhoz készült, beleértve a **Hisense 65E8S** modellt. A TV-re nem kell alkalmazást telepíteni: a beépített böngészőben jelenik meg a PC képe.

> **Állapot:** első, tesztelésre kész MVP. A helyi hálózati streamet és az API-t automatikus tesztek fedik le, de valódi Hisense 65E8S készüléken még nincs ellenőrizve.

## Használat

1. A [GitHub Actions](../../actions/workflows/windows-build.yml) sikeres legutóbbi buildjében töltsd le a **TVPCCast-Windows** artifactot, csomagold ki, és futtasd a **TVPCCast-Setup.exe** telepítőt. Verziótag kiadásakor a telepítő a [Releases](../../releases) oldalra is kikerül.
2. Nyisd meg a **TV-PC Cast** alkalmazást a Windows gépen.
3. Válaszd ki a monitort, felbontást és képkockaszámot, majd kattints a **Kivetítés indítása** gombra.
4. A Hisense TV-n nyisd meg a **Browser / Böngésző** alkalmazást, és írd be a PC alkalmazásban látható címet, pl. \`http://192.168.1.23:8765\`.
5. Írd be a PC-n megjelenő **6 jegyű PIN-t**. Megjelenik a képernyő élő képe.

Mindkét készüléknek ugyanazon a helyi hálózaton kell lennie. A PC és a TV lehet külön 2,4 GHz / 5 GHz sávon, ha a router engedi az eszközök közötti kommunikációt.

## Tudnivalók

- **Kép:** JPEG képkockák helyi HTTP kapcsolaton (MJPEG stream + egyesével frissülő JPEG tartalék mód).
- **Felbontás:** maximum 720p / 1080p / 1440p, 6–15 képkocka/másodperc.
- **Hang:** jelenleg nincs továbbítva.
- **Késleltetés:** Wi-Fi és TV-böngésző függő; nem alkalmas kompetitív játékra.
- **Biztonság:** egyedi PIN és munkamenet-token; a közvetítés kizárólag a PC-n indítható. A telepítő csak a Windows *privát* hálózati profilján engedélyezi a szükséges TCP portot. A HTTP forgalom a helyi hálózaton nincs titkosítva: ne használd nyilvános Wi-Fi-n.
- **DRM:** egyes védett videók fekete képként jelenhetnek meg.
- **TV kompatibilitás:** a Hisense VIDAA böngésző támogatása firmware-változattól is függ. Ha az MJPEG lejátszás nem működik, a weboldal automatikusan JPEG-enkénti frissítésre vált.
- **Nem Miracast / Chromecast:** a TV böngészőjén keresztül működik; a natív Windows \`Win + K\` vezeték nélküli kijelzőkeresése ettől független.

## Fejlesztői futtatás

Windows 10/11, Python 3.12+:

\`\`\`powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
\`\`\`

Tesztelés:

\`\`\`powershell
pip install pytest
python -m pytest -q
\`\`\`

## Windows .exe és telepítő

A \`.github/workflows/windows-build.yml\` minden \`main\` push-ra és manuális futtatásra Windows runneren készít:
- \`TVPCCast.exe\` — telepítés nélkül futtatható változat (PyInstaller)
- \`TVPCCast-Setup.exe\` — Windows telepítő (Inno Setup)

A \`v*\` verziótageknél a GitHub Actions Release-hez csatolja a két fájlt.

## Hibaelhárítás

- **A TV nem találja a címet:** ellenőrizd az IP-címet, a privát Windows hálózatot, a router AP/client isolation beállítását és a tűzfalat.
- **Mobilról megy, TV-ről nem:** a TV VIDAA böngészője lehet korlátozott; frissíts firmware-t, és próbáld a JPEG tartalék módot.
- **Fekete vagy álló kép:** ellenőrizd, hogy a megfelelő monitort választottad ki, és hogy a Windows nincs zárolva.
- **Akadozás:** válassz 720p / 10 FPS-t, használj 5 GHz-es Wi-Fi-t vagy LAN kábelt.
- **Tűzfal:** a telepítő létrehozza a *TV-PC Cast (Private)* bejövő szabályt TCP/8765 portra; portable futtatásnál ezt kézzel kell engedélyezni.
- **Ha a TV tud natív vezeték nélküli kijelzőt:** Windows \`Win + K\` billentyűkkel külön szoftver nélkül is kipróbálható.

## Licenc

MIT — lásd [LICENSE](LICENSE).
