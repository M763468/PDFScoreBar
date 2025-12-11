# Ideas & Notes

This area is reserved for free-form thinking, scratchpad notes, and future ideas.
It is not part of the formal documentation or development log.

- **FP Reduction**: 
    - かすれたバーラインを「複数の短い線」として検出してしまうのが原因なら、pdfの画像を超解像などにかけて画質をよくしてから処理するとうまくできる可能性がある。
    - 超解像以外にもbarline候補の縦線を上下に少し延長（画質が悪くて複数の短い線になっているのがつながる程度）してから判断することで過去に試した方策でもより良い結果が得られる可能性がある。

- **全体**
    - 行ごとの判断とかしている部分があると時間がかかる→並列化すると早くできそう
    - 将来的に複数ページのものを処理する場合も適切な並列処理を入れないとかなり時間がかかることになりそう。
