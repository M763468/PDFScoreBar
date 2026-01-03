# Measure Numbering Schema

This document defines the input and output JSON schemas for the measure numbering module.
The goal is to decouple the measure numbering logic from the specific barline detection implementation and rendering.

## Input Schema (`barlines`)

The input represents the structure of the music score as detected by the OMR system. It focuses on the hierarchy of Pages, Staff Systems, and Barlines.

### Structure

- **pages**: List of `Page` objects.

#### Page
- **index**: Integer (0-based index of the page).
- **systems**: List of `StaffSystem` objects on this page.

#### StaffSystem
- **index**: Integer (0-based index of the system within the page).
- **barlines**: List of `Barline` objects in this system, sorted by horizontal position (x-coordinate).

#### Barline
- **x**: Integer or Float (Horizontal position).
- **type**: String (Type of barline, e.g., "SINGLE", "DOUBLE", "END", "REPEAT_START", "REPEAT_END"). Default can be "SINGLE".

### Example JSON (Input)

```json
{
  "pages": [
    {
      "index": 0,
      "systems": [
        {
          "index": 0,
          "barlines": [
            { "x": 50, "type": "SINGLE" },
            { "x": 200, "type": "SINGLE" },
            { "x": 350, "type": "DOUBLE" }
          ]
        },
        {
          "index": 1,
          "barlines": [
            { "x": 50, "type": "SINGLE" },
            { "x": 200, "type": "SINGLE" },
            { "x": 350, "type": "END" }
          ]
        }
      ]
    }
  ]
}
```

## Output Schema (`measures`)

The output defines the identified measures and their corresponding numbers. A measure is defined as the region between two points (typically barlines).

### Structure

- **measures**: List of `Measure` objects.

#### Measure
- **number**: Integer or String (The assigned measure number).
- **start_barline_ref**: `BarlineReference` (The barline that starts this measure).
- **end_barline_ref**: `BarlineReference` (The barline that ends this measure).

#### BarlineReference
A reference to a specific barline in the input structure.

- **page_index**: Integer
- **system_index**: Integer
- **barline_index**: Integer (Index into the `barlines` list of the specified system)

*Note: For measures that start at the beginning of a system without an explicit barline, a convention or special value might be needed. For this schema, we assume measures are bounded by barlines or the numbering system handles implicit starts by referencing the first barline as the 'end' of the first region, etc. However, strictly following "reference to input barline", we use the indices.*

### Example JSON (Output)

```json
{
  "measures": [
    {
      "number": 1,
      "start_barline_ref": { "page_index": 0, "system_index": 0, "barline_index": 0 },
      "end_barline_ref": { "page_index": 0, "system_index": 0, "barline_index": 1 }
    },
    {
      "number": 2,
      "start_barline_ref": { "page_index": 0, "system_index": 0, "barline_index": 1 },
      "end_barline_ref": { "page_index": 0, "system_index": 0, "barline_index": 2 }
    }
  ]
}
```
