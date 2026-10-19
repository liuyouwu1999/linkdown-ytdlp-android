# yt-dlp-android · linkdown 引擎库 fork

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Android-lightgrey)

[linkdown（链接小卖部）](https://github.com/liuyouwu1999/linkdown) 的下载引擎库 fork。上游
[yausername/youtubedl-android](https://github.com/yausername/youtubedl-android)（MIT）的维护中
后继 `dev.ffmpegkit-maintained` 线的改动版，License 不变（MIT，见 LICENSE）。

本项目改动：

- per-run 取消注册表：`YtDlp.requestCancel(runId)` / `execute[Debug](runId, ...)`（宿主侧可精确取消单次执行）
- CLI 旗标白名单 `_FLAG_MAP` 扩展：`--flat-playlist`、`--dump-single-json`、`--no-playlist`、
  `--ffmpeg-location`、`--write-thumbnail`、`--skip-download`、`--audio-format` 等
- `setNativeLibDir`：注入宿主自建的 ffmpeg CLI 目录
- stdout→日志桥接（`--dump-single-json` 输出经日志回调回收）

## 构建（发布到 mavenLocal 供 linkdown 主仓库依赖）

```bash
./gradlew publishToMavenLocal                # 仓库根执行；产物 dev.ffmpegkit-maintained:yt-dlp-android:2.0.4
```



## 集成（JitPack）

本 fork 经 JitPack 分发，Maven 坐标与上游相同（`dev.ffmpegkit-maintained:yt-dlp-android`），版本号顺延上游线（2.0.4 起）。
**注意解析顺序**：本 fork 构件只存在于 JitPack / mavenLocal；Maven Central 上同坐标是上游官方 2.0.2——JitPack 必须声明在 mavenCentral 之前，否则会静默拿到未打补丁的上游版本。

```groovy
repositories {
    maven { url 'https://jitpack.io' }   // 必须在 mavenCentral 之前
    mavenCentral()
}
dependencies {
    implementation 'dev.ffmpegkit-maintained:yt-dlp-android:2.0.4'
}
```

版本号对应本仓库 git tag（发布时打 `2.0.4` tag 触发 JitPack 构建）；也可用提交哈希锁版本。

## 与上游的差异

- API 不兼容点：`YtDlp.execute[Debug]/executeAsync` 首参为 `runId`（per-run 取消注册表键），从上游 2.0.2 迁移需同步修改调用点。
- `alias-*` / `compat` 兼容模块依赖同坐标 `2.0.4`，第三方全新 clone 需先在仓库根执行 `./gradlew :library:publishToMavenLocal`，再构建全仓。

## 上游文档

功能总览、Cookie 认证、受支持站点列表等完整文档见上游仓库：
[ffmpegkit-maintained/yt-dlp-android](https://github.com/ffmpegkit-maintained/yt-dlp-android)（README 与 wiki）。


## License

MIT — see [LICENSE](LICENSE)

## Third-Party Notices

Third-party components bundled or built into this project retain their original
licenses. See [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt), which is also copied
into the AAR assets at build time (readable at runtime via
`context.assets.open("THIRD-PARTY-NOTICES.txt")`).
