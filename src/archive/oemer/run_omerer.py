import os
import subprocess

def run_omerer_on_images(image_folder, output_folder, target_pages):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    image_files = [f"page_{i}.png" for i in target_pages]
    
    for image_file in image_files:
        image_path = os.path.join(image_folder, image_file)
        
        # MusicXMLの出力ファイル名
        base_name = os.path.splitext(image_file)[0]
        output_musicxml_path = os.path.join(output_folder, f"{base_name}.musicxml")

        # oemer.ete の実行コマンドを構築
        command = [
            "python",
            "-m", "oemer.ete", # oemer の ete モジュール実行
            image_path, # 画像パス
            "--output-path", output_folder # 出力ディレクトリ
        ]
        
        print(f"Running oemer on {image_file}...")
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")
            print(f"Successfully processed {image_file} to {output_musicxml_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error processing {image_file}: {e}")
            print(f"Command: {' '.join(e.cmd)}")
            print(f"Stdout: {e.stdout}")
            f = open("omerer_error.log", "a")
            f.write(f"Stderr: {e.stderr}\n")
            f.close()

if __name__ == "__main__":
    image_dir = "/workspace/data/evaluation/images"
    output_dir = "/workspace/output/oemer"
    # 楽譜が映っているページ番号を指定 (3ページ目のみ)
    target_pages = [3]
    run_omerer_on_images(image_dir, output_dir, target_pages)
