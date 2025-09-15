import json
import matplotlib
matplotlib.use('TkAgg')  # または 'Qt5Agg' など
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import cv2

def visualize_measures(image_path, json_path):
    # JSONデータを読み込む
    with open(json_path, 'r') as f:
        data = json.load(f)

    # 画像を読み込む
    image = cv2.imread(image_path)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Matplotlibで画像を表示
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.imshow(image)

    # 矩形と小節番号を描画
    for measure in data:
        barline = measure["barline_location"]
        measure_number = measure["measure_number"]

        # 矩形を描画
        rect = patches.Rectangle(
            (barline[0], barline[1]),  # 左上の座標
            barline[2] - barline[0],  # 幅
            barline[3] - barline[1],  # 高さ
            linewidth=2,
            edgecolor='red',
            facecolor='none'
        )
        ax.add_patch(rect)

        # 小節番号を描画
        ax.text(
            barline[0], barline[1] - 10,  # テキストの位置
            str(measure_number),
            color='blue',
            fontsize=10,
            fontweight='bold'
        )

    # 表示
    plt.axis('off')
    plt.show()

if __name__ == "__main__":
    # 入力画像とJSONファイルのパス
    image_path = "data/training_images/page_1.png"
    json_path = "data/ground_truth_page_1_sorted.json"

    visualize_measures(image_path, json_path)