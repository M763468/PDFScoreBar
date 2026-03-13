## ブランチ運用
- Base branch: investigate/sr-optimization
- Branch name: task/realesrgan-x2-integration
- PR base: investigate/sr-optimization

## Goal
現在の Real-ESRGAN x4 モデル（およびダウンスケールによる擬似 x2）に代わり、ネイティブな x2 モデル（RealESRGAN_x2plus）を導入・検証し、SR 処理自体の高速化と精度のバランスを最適化する。

## Done
- [ ] RealESRGAN_x2plus.pth モデルを `external/realesrgan/weights/` に正しく配置（ダウンロード）している。
- [ ] `src/common/preprocessing.py` の `apply_advanced_sr` がネイティブ x2 モデルをサポートしている。
- [ ] x4 と x2 の処理時間および精度（F1スコア）の比較レポートを作成している。

## Notes
- x4 モデルを `outscale=2` で動かすだけでは、推論コスト自体は x4 と変わらず、時間短縮のメリットが薄い。
- 小節線の分離能力（網羅性）が x2 でも維持されるか、Prokofiev page 1 等の密集サンプルで検証が必要。
