import json
import os


def main():
    config_path = "tools/gt_relabel_gui/evaluation2_config.json"
    if not os.path.exists(config_path):
        print(f"Config not found: {config_path}")
        return

    with open(config_path, "r") as f:
        config = json.load(f)

    pages = config.get("pages", [])
    print(f"Checking {len(pages)} pages in config...")

    missing_files = []
    empty_files = []
    ok_count = 0

    for page in pages:
        name = page.get("name")
        editable_path = page.get("editable")

        if not editable_path:
            print(f"[MISSING PATH] {name}: No 'editable' path in config")
            missing_files.append(name)
            continue

        if not os.path.exists(editable_path):
            print(f"[FILE NOT FOUND] {name}: {editable_path}")
            missing_files.append(name)
        else:
            # Check if empty (or just empty list "[]")
            try:
                if os.path.getsize(editable_path) == 0:
                    print(f"[EMPTY FILE] {name}: {editable_path}")
                    empty_files.append(name)
                else:
                    with open(editable_path, "r") as f:
                        data = json.load(f)
                    if not isinstance(data, list):
                        print(f"[INVALID FORMAT] {name}: Not a list")
                        empty_files.append(name)  # effectively unusable
                    elif len(data) == 0:
                        print(f"[NO BOXES] {name}: JSON is empty list []")
                        # This might be valid if there are no barlines, but worth noting
                        # For now, let's assume it *might* be an issue if it's unexpected,
                        # but "No Peak" usually generates *too many*.
                        # If we used 0.5 threshold CNN, maybe 0 survived?
                        pass

                    ok_count += 1
            except json.JSONDecodeError:
                print(f"[JSON ERROR] {name}: Could not decode JSON")
                empty_files.append(name)

    print("-" * 30)
    print(f"Total Pages: {len(pages)}")
    print(f"OK (File Exists & Valid JSON): {ok_count}")
    print(f"Missing Files: {len(missing_files)}")
    print(f"Empty/Invalid Files: {len(empty_files)}")


if __name__ == "__main__":
    main()
