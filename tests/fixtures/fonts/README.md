# The suite's font

DejaVu Sans 2.37, regular and bold, as its project publishes them:
<https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37>
(`dejavu-fonts-ttf-2.37.tar.bz2`, SHA-256
`fa9ca4d13871dd122f61258a80d01751d603b4d3ee14095d65453b4e846e17d7`). The same
version the CI's `fonts-dejavu-core` installs.

`tests/qt.py` loads them where the system has no DejaVu Sans, so a width
measured on any desktop is the one the CI measures. They are not part of the
program: no package carries them. Their licence is in `LICENSE`, here.
