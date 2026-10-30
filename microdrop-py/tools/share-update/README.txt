{title}
{title_rule}

This update brings the MicroDrop you already have up to date - the plugins
and the packages MicroDrop runs on - without reinstalling it. No internet
connection is needed.

It installs {count} packages, including these plugins:

{plugins}


1. Unzip this download INSIDE your MicroDrop folder - the folder with
   install.bat, run-microdrop.bat and the env folder - so that it holds a
   new {folder_name} folder next to env.

2. Close MicroDrop.

3. Open the {folder_name} folder and double-click
   apply-update.bat   (takes a few minutes).

4. Start MicroDrop again as usual.

If apply-update.bat cannot find MicroDrop next to it, it asks for the
MicroDrop folder: type or paste its path (e.g. C:\MicroDrop) and press Enter.


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
apply-update.bat    installs the update into ..\env
channel\            the updated packages
micromamba.exe      package installer used by apply-update.bat
fix-conda-meta.py   prepares the install's package records for micromamba
update.json         what this update contains and which installs it is for
specs.txt           the exact package versions apply-update.bat installs
optional-specs.txt  build tools updated only where they are installed
plugins.txt         the plugins whose versions apply-update.bat shows
