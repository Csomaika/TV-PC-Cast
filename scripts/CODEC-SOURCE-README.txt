TV-PC Cast Windows x64 corresponding source

The app source and build/installation scripts are in TVPCCast-source.
See requirements.txt and scripts/build-windows.ps1 in that directory.
This archive accompanies TVPCCast-Setup.exe and TVPCCast-Portable.zip.

The wheel archive listed in pyav-windows-wheel.json is PyAV v19.0.2,
commit a4ad0133b13eb84067dc6e8105eb1fc8f8b93c4f. The bundle builder
checks that every shipped DLL matches that exact win_amd64 wheel.
The upstream PyAV build used the vendor specified by its
scripts/ffmpeg-latest.json, pyav-ffmpeg 9.0.2-1, commit
bac889417e26be29615cb6a3f38318151fed55cd. The published vendor run is
https://github.com/PyAV-Org/pyav-ffmpeg/actions/runs/35461333227.

The upstream directory has the PyAV sdist, both upstream build trees,
the original FFmpeg 9.0.2 tarball and the Windows build dependencies.
The vendor build tree provides scripts/build-ffmpeg.py, the Windows
MINGW64 recipe in .github/workflows/build-ffmpeg.yml, scripts/pkg.py
and the original patches. Use the patches and recipe together with the
listed source archives. The PyAV source tree includes its wheel build
and delvewheel-repair recipe in .github/workflows/tests.yml.

The lamer upstream repository has been renamed bwlame. The v3.101.0 tag
names commit 3ffd14f5531e0e5078e31eba4b2fb6ccc277b843. Its regenerated
GitHub archive uses the bwlame-3.101.0 directory and a new SHA-256;
codec-sources.json records that file's hash. The build recipe expects
the local archive filename lamer-3.101.0.tar.gz.

The MSYS2 source packages contain their build metadata, original sources
and patches. GCC 16.1.0-5, libiconv 1.19-1 and zlib 1.3.2-2 match the
loaded sections of the vendor DLLs after upstream stripping. Both June
MinGW-w64 winpthreads packages with matching loaded sections are provided
because the upstream strip step replaced the original PE timestamps and
the two source package revisions cannot be separated by those sections.

The checksums and upstream retrieval URLs are in codec-sources.json.
Third-party copyright and license texts are in THIRD-PARTY-LICENSES and
in the source archives. See THIRD-PARTY-NOTICES.txt for release terms.
