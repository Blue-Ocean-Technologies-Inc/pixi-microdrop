{title}
{title_rule}

MicroDrop's environment is packed in this folder, so installing it needs no
internet connection and no conda packages from outside. MicroDrop itself is
a git copy (.\microdrop) of the Microdrop repository's main branch: run
update-microdrop.bat to pull the latest version at any time.

1. Put this folder where you want MicroDrop to live, e.g. C:\MicroDrop.
   Pick the final location first: the install is tied to the folder path.

2. Double-click  install.bat   (once; takes about 10 minutes, needs ~6 GB
   free, under 1 GB once done).

3. Start MicroDrop with the "MicroDrop" shortcut (created in this folder and
   on your Desktop by install.bat), or double-click run-microdrop.bat.

4. To update MicroDrop, close it and double-click update-microdrop.bat.
   It needs access to github.com.


Other devices
-------------
run-microdrop.bat starts MicroDrop for the DropBot. For another device, run
it from a Command Prompt with a --device option:

    run-microdrop.bat --device opendrop
    run-microdrop.bat --device mock        (no hardware, for trying it out)


Updates
-------
update-microdrop.bat only updates MicroDrop's own code. Occasionally an
update also needs a newer environment (new packages); MicroDrop will then
fail to start with a "No module named ..." error. Get a new copy of this
download in that case - the updates themselves never need one otherwise.


Troubleshooting
---------------
- "Windows protected your PC": click "More info" then "Run anyway". The
  scripts are unsigned.
- Moved or renamed the folder: run install.bat again and answer Y. This
  needs the .tar file; if you let install.bat delete it, unzip the
  download again first.
- An update stops with a message about local changes: the files in
  .\microdrop were edited. Unzip a fresh copy of the download.
- To uninstall: delete this folder (and its shortcut on the Desktop).


Files
-----
install.bat           unpacks the environment into .\env
run-microdrop.bat     starts MicroDrop
update-microdrop.bat  pulls the latest MicroDrop into .\microdrop
microdrop\            MicroDrop itself, a git clone of the main branch
pixi-unpack.exe       unpacker used by install.bat
{pack_name}
                      the packed environment; install.bat offers to delete
                      it once done. Keep it if you may move the folder later.
models\               AI model weights (EfficientSAM, ~100 MB); install.bat
                      copies them to %USERPROFILE%\.cache\osam so AI ROI
                      detection works without internet. Other models picked
                      in Preferences download on first use.

MicroDrop {version} at packing time
