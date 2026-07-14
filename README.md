# Getting Started with Pixi for Microdrop

This guide provides instructions on how to set up and run the [Microdrop](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop) project using [Pixi](https://pixi.sh/dev/installation).

## Requirements:
- Install [Pixi](https://pixi.sh/dev/installation).
- Run `git clone --recursive https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop.git`

## Easy Way On Windows
Click on `microdrop.bat`

## Mac and Linux

```shell
sh run_microdrop.sh
```

## Manual way
1. Navigating to the microdrop-py directory:

```shell
cd microdrop-py
```


2. Initializing and updating Submodules if you cloned the repository without using the --recursive flag, or if you need to update any nested repositories, run the following command to initialize and update all submodules:

```shell
git submodule update --init --recursive`
```
  

3. To start the Microdrop application, use the pixi command with the following script:

```shell
pixi run microdrop
```

