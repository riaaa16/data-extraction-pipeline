# UI Specifications: AI Data Structuring Pipeline

## Overview
This UI follows a guided, linear workflow:
Upload → Schema → Processing → Results

Each screen includes:
- Purpose
- Components
- ASCII Wireframe

---

## 1. Upload Screen

### Purpose
Allow users to upload unstructured data files.

### Components
- File upload (drag & drop)
- Uploaded file list
- Continue button

Accepted file types: `.pdf`, `.txt`, `.docx`.

### Wireframe
```
[ Upload Files ]
[ Drag & Drop Area ]

Files:
- file1.pdf

[ Continue → ]
```

---

## 2. Schema Builder

### Purpose
Define extraction schema.

### Components
- Field list
- Field editor (name, type, enum)
- Add field button
- Run button

### Wireframe
```
Fields:
[ date | string ]
[ platform | string ]
[ sentiment | enum: positive, neutral ]

[ + Add Field ]

[ Run Processing ]
```

---

## 3. Processing Screen

### Purpose
Show pipeline progress.

### Components
- Progress bar
- Status text
- Metrics

### Wireframe
```
Progress: [#####-----] 50%

Step: Processing entries (10/20)

Entries: 20
Processed: 10
```

---

## 4. Results Screen

### Purpose
Display structured data.

### Components
- Table
- Filters
- Export CSV

### Wireframe
```
ID | date | platform | confidence
1  | 1/2  | YouTube  | 0.82

[ Export CSV ]
```

---

## 5. Entry Detail

### Purpose
Inspect and edit outputs.

### Components
- Raw text
- Structured fields
- Save button

### Wireframe
```
RAW TEXT        | STRUCTURED
---------------|-----------
"text..."      | date: 1/2
               | platform: YouTube

[ Save ]
```

---

## 6. Insights

### Purpose
Show aggregated data.

### Components
- Summary stats
- Theme counts

### Wireframe
```
Themes:
confusion (10)
engagement (8)

Platform:
YouTube (12)
Book (7)
```
