## ブランチ運用
- Base branch: investigate/sr-optimization
- Branch name: investigate/shm-expansion
- PR base: investigate/sr-optimization

## Goal
Dockerコンテナ（sr_eval_gpu）の共有メモリ（/dev/shm）サイズを現在のデフォルト（64MB）から拡張し、超解像（SR）後の大規模な画像データ（数百MB〜GB単位）を高速にプロセス間で転送可能にする。

## Done
- [ ] Makefile または起動スクリプトにおいて、--shm-size パラメータ（推奨: 2GB以上）を追加・検証している。
- [ ] コンテナ内から df -h /dev/shm を実行し、指定したサイズが正しく反映されていることを確認している。
- [ ] 共有メモリを利用した画像データ転送のプロトタイプまたは検証コードが動作することを確認している。

## Notes
- Issue #25 の調査において、現状の 64MB では大規模 SR 画像の転送に不十分であることが判明した。
- RTX 4060 (8GB VRAM) 環境での並列処理を考慮すると、余裕を持ったサイズ設定が望ましい。
