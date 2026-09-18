## [v0.5.0](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/releases/tag/v0.5.0) (2026-09-18)

### Feat

- **tools**: add a clean-dist task for the pack intermediates ([`703574d`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/703574d36c4f9c4a52cb3d8e5e20bc1ac89edce7))

## [v0.4.0](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/releases/tag/v0.4.0) (2026-09-18)

### Feat

- **share**: offer to delete the pack once installed ([`c495c3a`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/c495c3aea1031f645c9799211f1ff0f0eb9cf2d5))
- **share**: retire previous installs when a new version lands ([`41597fe`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/41597feae868fabb4aeb82bba7730ad4f7f5aa52))
- **share**: name the shortcut after the installed version ([`4f2ac2c`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/4f2ac2c89167bdb81727c57a1db8aed11f926309))

### Perf

- **share**: compress the install with XPRESS16K instead of LZX ([`c19aa7f`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/c19aa7fbfe87e4e8ebc15ff975328fd80c5689e1))

## [v0.3.1](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/releases/tag/v0.3.1) (2026-09-18)

### Fix

- **launcher**: import the portable backend plugin lazily ([`7253aa6`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/7253aa689c9281d4e61234dafcd1a3899dd12a36))

## [v0.3.0](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/releases/tag/v0.3.0) (2026-09-17)

### Feat

- **pixi**: add share-prod-all for both hand-off zips ([`2d8da61`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/2d8da6176384107c8b5913ef6c61f3c25332b24c))
- generate the offline hand-off with share-prod ([`1713319`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/1713319fe96e9f08ae23de294e6f4c2280dab739))
- strip the build toolchain from prod packs ([`2b947dc`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/2b947dcce5e0e0129dcc2fe557a5ec3cd6792dee))
- **pixi**: add prod environments and pack tasks ([`c1efc06`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/c1efc06eb03b1a9ed04d89283db46f99aa21fe74))

### Fix

- refuse a hand-off built from uncommitted src ([`ce9bdd9`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/ce9bdd9aa37bf85ef93c0fa813182d90224be16e))

### Refactor

- move the pack scripts into microdrop-py/tools ([`a913d78`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/a913d78b8cbe25b0dd7d093da4419f3fe3f28333))
- **pixi**: keep clone-run plugins out of dev envs ([`3492801`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/3492801c6ea11c2a6a7131abdfd0e4a3540f6de4))

## [v0.2.0](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/releases/tag/v0.2.0) (2026-09-15)

### Feat

- **pixi**: add dropbot-portable-ui, target glibc 2.41 ([`7a52abe`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/7a52abe5a2f7b9cc18718cee2f78b16d2c1b39de))

### Fix

- **pixi**: allow PySide6 6.11 and preload system ICU ([`d3c5d78`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/d3c5d78af9dd8c78fe5410c81627445e1015a76c))
- add pyside6-icu-preload startup package ([`20187d9`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/20187d9d8ce0b1fd2bcfbfddff91f167b3a81c0c))

## [v0.1.0](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/releases/tag/v0.1.0) (2026-09-01)

### Feat

- **launcher**: resolve default plugins for the portable device ([`6ac00b9`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/6ac00b98b078c7221368edfe7f855b2eb28d5a91))
- frozen-exe support + new-installation flow in setup script ([`aaa32f4`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/aaa32f43c888e8e8e3ec82bbd5a1f3b13768f1e7))
- fluorescence plugin as editable dep in default env ([`736a2f5`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/736a2f5df3c23dc07025814f0575160b498430ac))

### Fix

- add portable dropbot device choice in microdrop.py ([`67c8f5e`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/67c8f5e65399a601f438bbee3ecbc035923f6d5e))
- checkout main when src has no branch ([`0bd3b74`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/0bd3b74e4138f1fc1b2a001e320cf34f57e62d25))
- **packaging**: sync wheel packages list with the actual src tree ([`31f5325`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/31f532515fd57be929b4617eec566314ee05729d))

### Refactor

- **packaging**: auto-include src packages in the wheel ([`b3ffa70`](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop/commit/b3ffa70f03f8d4b12c57c2a981b6c0075ef44dcc))
