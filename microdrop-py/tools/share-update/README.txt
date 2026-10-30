{title}
{title_rule}

This update brings the MicroDrop you already have up to date - the plugins
and the packages MicroDrop runs on - without reinstalling it. No internet
connection is needed.

It installs {count} packages, including these plugins:

{plugins}

{microdrop}


1. Unzip this download anywhere (a short path such as C:\mdupdate avoids
   Windows' long-path limit). It holds one {folder_name} folder; Windows'
   "Extract All" may put it inside a folder named after the zip, which is
   fine.

2. Close MicroDrop.

3. Open the {folder_name} folder, double-click apply-update.bat and enter
   your MicroDrop folder (the one with the env folder) when asked, e.g.
   C:\MicroDrop - or just press Enter if it already shows the right one.
   The update takes a few minutes.

4. Start MicroDrop again as usual.

If Windows says the path is too long while unzipping, extract the zip to a
short folder such as C:\mdupdate instead and run apply-update.bat from
there.

To skip the question, pass the folder to the script from a command prompt:
    apply-update.bat "C:\MicroDrop"


Going back
----------
To return to the versions MicroDrop shipped with, run install.bat in your
MicroDrop folder again and answer Y to reinstall. That needs the .tar file
from the original download; if install.bat says it is missing, unzip the
original MicroDrop download again first.


Troubleshooting
---------------
- "Windows protected your PC": click "More info" then "Run anyway". The
  script is unsigned.
- If the update fails, see "Going back" above, and tell us which MicroDrop
  download you installed from: update.json lists the downloads this update
  was made for.
- Once the update is done, this folder can be deleted.


Files
-----
apply-update.bat    installs the update into your MicroDrop's env folder
channel\            the updated packages
wheels\             the updated Python (PyPI) packages, installed after them
micromamba.exe      package installer used by apply-update.bat
fix-conda-meta.py   prepares the install's package records for micromamba
update.json         what this update contains and which installs it is for
specs.txt           the exact package versions apply-update.bat installs
optional-specs.txt  build tools updated only where they are installed
plugins.txt         the plugins whose versions apply-update.bat shows
pypi-specs.txt      the exact Python package versions it installs
microdrop-spec.txt  the MicroDrop version it installs (not into a git install)
