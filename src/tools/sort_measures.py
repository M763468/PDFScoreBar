import json

def group_and_sort_measures(input_file, output_file):
    with open(input_file, 'r') as f:
        data = json.load(f)

    # グループ化のための閾値
    y_threshold = 50

    # 段ごとにグループ化
    groups = []
    for measure in data:
        y_center = (measure["barline_location"][1] + measure["barline_location"][3]) / 2
        added = False
        for group in groups:
            group_y_center = (group[0]["barline_location"][1] + group[0]["barline_location"][3]) / 2
            if abs(y_center - group_y_center) < y_threshold:
                group.append(measure)
                added = True
                break
        if not added:
            groups.append([measure])

    # 各グループ内でX座標を基準にソート
    for group in groups:
        group.sort(key=lambda x: x["barline_location"][0])

    # 小節番号を更新
    sorted_data = []
    measure_number = 1
    for group in groups:
        for measure in group:
            measure["measure_number"] = measure_number
            sorted_data.append(measure)
            measure_number += 1

    # 結果を保存
    with open(output_file, 'w') as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    input_file = "data/ground_truth_page_1_new.json"
    output_file = "data/ground_truth_page_1_sorted.json"
    group_and_sort_measures(input_file, output_file)