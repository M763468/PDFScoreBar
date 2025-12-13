# Ideas & Notes

This area is reserved for free-form thinking, scratchpad notes, and future ideas.
It is not part of the formal documentation or development log.

- **FP Reduction**: 
    - homrの最終的なフローはどうなっている？楽譜の行ごとの処理と化していたような気がする
       - omr-dlnにも「行ごとの処理」を適用すると改善する可能性がある？
    - 過去に実験した各種ヒューリスティックな後処理は一つの値で試しただけではなかったか
        - 特にnoteheadとの接触は適切なに行えばもう少し改善できると思っていた。
        - 何がどう失敗したかの調査や、後処理におけるパラメータの調節によるよい結果の探索もしていいのかも。

- **全体**
    - 行ごとの判断とかしている部分があると時間がかかる→並列化すると早くできそう
    - 将来的に複数ページのものを処理する場合も適切な並列処理を入れないとかなり時間がかかることになりそう。
