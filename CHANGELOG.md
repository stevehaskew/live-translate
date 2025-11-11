# Changelog

## 1.0.0 (2025-11-11)


### Features

* add verbose logging to speech_to_text ([a75dd45](https://github.com/stevehaskew/live-translate/commit/a75dd45090658fbd01df51f52bb400c5897a24af))
* containerise server side of application ([e345dc3](https://github.com/stevehaskew/live-translate/commit/e345dc3b00913dbd4c12b26f5db27586e374359a))
* implement collapsible settings panel and condensed mobile layout ([#19](https://github.com/stevehaskew/live-translate/issues/19)) ([176195b](https://github.com/stevehaskew/live-translate/commit/176195bdebc8b0ba8b2806770a303aaa568d29a5))
* implement go speech-to-text client with AWS Transcribe Streaming ([#31](https://github.com/stevehaskew/live-translate/issues/31)) ([56c1ea0](https://github.com/stevehaskew/live-translate/commit/56c1ea055313eeca6033476a073e97d29828f427))
* implement in aws ([#42](https://github.com/stevehaskew/live-translate/issues/42)) ([e032a48](https://github.com/stevehaskew/live-translate/commit/e032a484f527736e8c092c3f09ea8b474c80ceb9))
* initial commit ([2dec4c0](https://github.com/stevehaskew/live-translate/commit/2dec4c0b5f73475c390db6f9db9d18a922d81937))
* migrate from Socket.IO to plain WebSockets ([#37](https://github.com/stevehaskew/live-translate/issues/37)) ([f049d98](https://github.com/stevehaskew/live-translate/commit/f049d9829653c41826277b8e891debcf18c1cb37))
* refactor message handling into reusable modules with DynamoDB support ([#40](https://github.com/stevehaskew/live-translate/issues/40)) ([f3a06a7](https://github.com/stevehaskew/live-translate/commit/f3a06a71407aabef202105dcbd3a449c478dbfe7))
* tidy up and add release-please ([#10](https://github.com/stevehaskew/live-translate/issues/10)) ([ec1da67](https://github.com/stevehaskew/live-translate/commit/ec1da67a6a938857d70e169caa4bea9a7725c192))
* translate per-language rather than per-client ([04c98ec](https://github.com/stevehaskew/live-translate/commit/04c98ec20a3a62b8228c9a722aa10b08cbcc4c56))
* ui customisation ([96f1dfc](https://github.com/stevehaskew/live-translate/commit/96f1dfc1bce2b5f4d97bc4388b089664bcba2040))


### Bug Fixes

* add api-key auth between client and server ([874e263](https://github.com/stevehaskew/live-translate/commit/874e2634518513e069296d57795eede35b35a220))
* add missing deps ([#16](https://github.com/stevehaskew/live-translate/issues/16)) ([76033c2](https://github.com/stevehaskew/live-translate/commit/76033c2b88df5baf23cbb85978864962794d1c06))
* clean up ui a little ([24f1d48](https://github.com/stevehaskew/live-translate/commit/24f1d487326fb6b8ef7a8db331d2a7d59cfb1549))
* default to port 5050 to avoid clash with airplay ([#8](https://github.com/stevehaskew/live-translate/issues/8)) ([1a51d48](https://github.com/stevehaskew/live-translate/commit/1a51d48f478fe647892edb1942e4cb988ddb8e19))
* fix docker version post latest changes ([e619a0f](https://github.com/stevehaskew/live-translate/commit/e619a0f413a0efa47d895ceaba1c5fb87d6146f2))
* fix python tests ([d7c3074](https://github.com/stevehaskew/live-translate/commit/d7c307471364e1eff9fe1a41e5b618ae36147f13))
* graceful shutdown for speech client ([309f7d0](https://github.com/stevehaskew/live-translate/commit/309f7d05c85e219df89f3d25c55b7159bc02d459))
* separate listening/recognition threads for continuous translation ([8d89fcd](https://github.com/stevehaskew/live-translate/commit/8d89fcda07f65fe7e49245041be5d027a4580bcf))
* store language for returning user ([cbc8b60](https://github.com/stevehaskew/live-translate/commit/cbc8b609e460a8a6d414edea563fb548ee088434))
* ui tweaks and gunicorn fixes ([988b2cf](https://github.com/stevehaskew/live-translate/commit/988b2cf917c30724ab38c8e729dd962178770772))
