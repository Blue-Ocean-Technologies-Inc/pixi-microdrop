{title}
{title_rule}
{variant_note}
Everything MicroDrop needs is in this folder. Nothing else has to be
installed, and no internet connection is needed.

1. Put this folder where you want MicroDrop to live, e.g. C:\MicroDrop.
   Pick the final location first: the install is tied to the folder path.

2. Double-click  install.bat   (once; takes about 10 minutes, needs ~6 GB
   free, under 1 GB once done).

3. Start MicroDrop with the "MicroDrop {version}" shortcut (created in this
   folder and on your Desktop by install.bat), or double-click
   run-microdrop.bat. The version in the name keeps several installed
   versions apart on the Desktop. Installing a newer version removes the
   older versions' Desktop shortcuts and offers to delete their folders.


Other devices
-------------
run-microdrop.bat starts MicroDrop for the DropBot. For another device, run
it from a Command Prompt with a --device option:

    run-microdrop.bat --device opendrop
    run-microdrop.bat --device mock        (no hardware, for trying it out)


Troubleshooting
---------------
- "Windows protected your PC": click "More info" then "Run anyway". The
  scripts are unsigned.
- Moved or renamed the folder: run install.bat again and answer Y. This
  needs the .tar file; if you let install.bat delete it, unzip the
  download again first.
- On a drive that is not NTFS the install still works, but it is not
  compressed and takes about 2 GB.
- To uninstall: delete this folder (and its shortcut on the Desktop).


Files
-----
install.bat         unpacks the environment into .\env
run-microdrop.bat   starts MicroDrop
pixi-unpack.exe     unpacker used by install.bat
{pack_name}
                    the packed environment; install.bat offers to delete
                    it once done (frees ~0.6 GB). Keep it if you may move
                    the folder later.
{models_entry}
MicroDrop {version}
