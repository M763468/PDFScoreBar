# Ideas & Notes

This area is reserved for free-form thinking, scratchpad notes, and future ideas.
It is not part of the formal documentation or development log.

- **FN, FPへの対処**:     


- **処理速度に関する問題**
    - 行ごとの判断をしている部分があると時間がかかる→並列化すると早くできそう：gpuを使っている部分で並列化するとよいはず。
        - 将来的に複数ページのものを処理する場合も適切な並列処理を入れないとかなり時間がかかることになりそう。
        - どこかのタイミングで並列化を考えるステップが必要
    - REAL-ESRGANが遅いという問題→ライブラリのバージョンの問題。basicsrにパッチを入れて解決できることが判明
        - 適切にGPUを使ったりすればもっと早かったはず。
        - モデルの初期化が毎回行われたりしていないか？
        - そもそもGPUが適切に使用できていない可能性もある。要調査。
        - REAL-ESRGAN以外の方法を使うならば、その超解像モデルを使っても効果が下がらないことを確認する必要がある。