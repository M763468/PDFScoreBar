import cv2
import numpy as np
import os

def add_measure_numbers(image_path, output_path, barlines):
    """
    Adds measure numbers to a score image based on a list of barline coordinates.

    Args:
        image_path (str): Path to the input score image.
        output_path (str): Path to save the output image with measure numbers.
        barlines (list): A list of tuples, where each tuple represents a barline
                         with ((x1, y1), (x2, y2)) coordinates.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image {image_path}")
        return

    # Group barlines into staves based on their y-coordinate
    staves = {}
    for (x1, y1), (x2, y2) in barlines:
        # Group y-coordinates in bands of 50px to identify staves
        staff_y_key = int(y1 / 50) * 50
        if staff_y_key not in staves:
            staves[staff_y_key] = []
        staves[staff_y_key].append(((x1, y1), (x2, y2)))

    measure_count = 1
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    font_color = (0, 0, 255)  # Red color for visibility
    thickness = 2

    # Process each staff system, sorted from top to bottom
    for staff_y_key in sorted(staves.keys()):
        staff_barlines = sorted(staves[staff_y_key], key=lambda line: line[0][0])

        # Define the start of the measure line for numbering purposes
        # Assumes music starts at a fixed x-coordinate
        start_x = 70
        first_barline_y_start = staff_barlines[0][0][1]
        first_barline_y_end = staff_barlines[0][1][1]
        
        # Create a list of measure dividers for this staff, including the start
        measure_dividers = [((start_x, first_barline_y_start), (start_x, first_barline_y_end))] + staff_barlines

        # Draw numbers for each measure on the staff
        for i in range(len(measure_dividers) - 1):
            left_bar = measure_dividers[i]
            right_bar = measure_dividers[i+1]

            # Calculate position for the measure number
            x_pos = (left_bar[0][0] + right_bar[0][0]) // 2
            y_pos = left_bar[0][1] - 15  # Place it 15px above the top of the barline

            # Draw the number
            cv2.putText(img, str(measure_count), (x_pos, y_pos), font,
                        font_scale, font_color, thickness, cv2.LINE_AA)
            measure_count += 1

    # Save the final image
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, img)
    print(f"Successfully created image with measure numbers at: {output_path}")


if __name__ == "__main__":
    # --- Configuration ---
    IMAGE_PATH = "data/input_images/page_3.png"
    OUTPUT_PATH = "output/gemini_opencv/page_3_with_measure_numbers.png"

    # This high-quality barline data is provided by Gemini.
    # In a future implementation, this could be fetched via an API call.
    high_quality_barlines = [
        # Staff 1: y ~138-178
        ((172, 138), (172, 178)), ((269, 138), (269, 178)), ((367, 138), (367, 178)), ((463, 138), (463, 178)),
        # Staff 2: y ~191-231
        ((75, 191), (75, 231)), ((172, 191), (172, 231)), ((269, 191), (269, 231)), ((367, 191), (367, 231)), ((463, 191), (463, 231)),
        # Staff 3: y ~250-290
        ((75, 250), (75, 290)), ((172, 250), (172, 290)), ((269, 250), (269, 290)), ((367, 250), (367, 290)), ((463, 250), (463, 290)),
        # Staff 4: y ~308-348
        ((75, 308), (75, 348)), ((172, 308), (172, 348)), ((269, 308), (269, 348)), ((367, 308), (367, 348)), ((463, 308), (463, 348)),
        # Staff 5: y ~365-405
        ((75, 365), (75, 405)), ((172, 365), (172, 405)), ((269, 365), (269, 405)), ((367, 365), (367, 405)), ((463, 365), (463, 405)),
        # Staff 6 (Menuetto): y ~458-498
        ((172, 458), (172, 498)), ((269, 458), (269, 498)), ((367, 458), (367, 498)), ((463, 458), (463, 498)), # Repeat bar
        # Staff 7: y ~515-555
        ((75, 515), (75, 555)), ((172, 515), (172, 555)), ((269, 515), (269, 555)), ((367, 515), (367, 555)), ((463, 515), (463, 555)),
        # Staff 8 (Trio): y ~598-638
        ((172, 598), (172, 638)), ((269, 598), (269, 638)), ((367, 598), (367, 638)), ((463, 598), (463, 638)), # Fine bar
        # Staff 9: y ~655-695
        ((75, 655), (75, 695)), ((172, 655), (172, 695)), ((269, 655), (269, 695)), ((367, 655), (367, 695)), ((463, 655), (463, 695)),
        # Staff 10 (FINALE): y ~745-785
        ((172, 745), (172, 785)), ((269, 745), (269, 785)), ((367, 745), (367, 785)), ((463, 745), (463, 785)), # Repeat bar
        # Staff 11: y ~802-842
        ((75, 802), (75, 842)), ((172, 802), (172, 842)), ((269, 802), (269, 842)), ((367, 802), (367, 842)), ((463, 802), (463, 842)), # Repeat bar
    ]

    # --- Execution ---
    add_measure_numbers(IMAGE_PATH, OUTPUT_PATH, high_quality_barlines)