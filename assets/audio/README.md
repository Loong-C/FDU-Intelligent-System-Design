# 本地合成测试音色

`audio_engine.synthesize_chords()` 启动时生成 C、G、Am、F 的上下扫音色并缓存为 float32 PCM；正弦波及谐波、指数衰减、每根虚拟琴弦 8 ms 起音间隔，力度线性缩放振幅。音源为本次新增的数学合成代码，无外部录音、网络下载或采样授权依赖。它是验证闭环的测试音色，不是最终吉他音色。

不提交生成的 WAV。如要替换为真实吉他采样，先核实可分发许可及署名，再在启动阶段预加载所有音源，继续使用原事件契约。

实际播放：`python audio_engine.py`；设备列表：`python audio_engine.py --list-devices`。PortAudio 输出流初始化失败会显式报告 error，主视觉服务仍可运行。mock/disabled 不表示设备发声。

后端参考：[sounddevice 0.5.3 OutputStream 官方文档](https://python-sounddevice.readthedocs.io/en/0.5.3/api/streams.html)。回调消费有界队列，最多 8 个重叠声部。队列满/超过 200 ms 的事件丢弃并计数，不无限积压。
