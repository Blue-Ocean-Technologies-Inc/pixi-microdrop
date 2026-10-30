{title}
{title_rule}

This update installs newer MicroDrop plugins, and any packages they need,
into the MicroDrop you already have, without reinstalling it. No internet
connection is needed.

It installs:

{install}


1. Unzip this download INSIDE your MicroDrop folder - the folder with
   install.bat, run-microdrop.bat and the env folder - so that it holds a
   new {folder_name} folder next to env.

2. Close MicroDrop.

3. Open the {folder_name} folder and double-click
   apply-update.bat   (takes about a minute).

4. Start MicroDrop again as usual.

If apply-update.bat cannot find MicroDrop next to it, it asks for the
MicroDrop folder: type or paste its path (e.g. C:\MicroDrop) and press Enter.


Going back
----------
To return to the plugin versions MicroDrop shipped with, run install.bat in
your MicroDrop folder again and answer Y to reinstall. That needs the .tar
file from the original download; if install.bat says it is missing, unzip
the original MicroDrop download again first.


Troubleshooting
---------------
- "Windows protected your PC": click "More info" then "Run anyway". The
  script is unsigned.
- A warning that the installed plugins differ: this update was made for
  the install from {base}. It usually still works; if the update then
  fails, see "Going back" above.
- Once the update is done, this folder can be deleted.


Files
-----
apply-update.bat  installs the plugins into ..\env
channel\            the plugin packages and the packages they need
micromamba.exe      package installer used by apply-update.bat
fix-conda-meta.py   prepares the install's package records for micromamba
update.json         what this update contains and which install it is for
specs.txt           the exact plugin versions apply-update.bat installs
base-plugins.txt    the plugin versions of the install it was made for
