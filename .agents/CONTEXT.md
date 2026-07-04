# Context: Frontend Redesign - ACRYLITEC

## Overview
This document describes the visual redesign of the ACRYLITEC Django project frontend, applying principles from the `impeccable` and `minimalist-ui` skills.

## Design Principles Applied

### From `impeccable`
- **Anti-AI-slop**: No Inter/Roboto/Open Sans fonts, no Lucide/Feather icons, no heavy shadows
- **Warm monochrome palette**: Uses warm grays (#fafaf8, #f5f5f0, #e8e6e1) instead of cool grays
- **Geometric sans + serif**: Outfit (geometric sans) + DM Serif Display (editorial serif)
- **Subtle motion**: CSS transitions for hover states, no heavy animations
- **Flat bento grids**: CSS Grid layouts instead of Bootstrap columns

### From `minimalist-ui`
- **No gradients or neon colors**: Flat, muted color palette
- **No heavy shadows**: Subtle, tinted shadows using warm colors
- **Editorial feel**: Typography contrast between headings and body
- **Clean components**: Minimal borders, generous padding

## Files Modified

### 1. `gestion/static/gestion/css/main.css` (NEW)
**Purpose**: Central design system file
**Content**:
- CSS Variables for colors, typography, spacing, shadows
- Base styles (reset, typography, links)
- Navbar styles (light background, warm borders)
- Card styles (flat, subtle borders)
- KPI card component (custom component with color variants)
- Table styles (clean, minimal)
- Button styles (all variants)
- Badge styles
- Form styles
- Alert styles
- Bento grid system (CSS Grid)
- Section styles
- Login page styles
- Dashboard-specific styles (KPIs, charts, actions)
- Period picker styles
- Empty state styles
- Utility classes
- Responsive breakpoints

### 2. `gestion/templates/gestion/base.html`
**Changes**:
- Added link to `main.css`
- Changed navbar from `navbar-dark bg-dark` to light with warm background
- Removed inline `<style>` block (mobile styles moved to main.css)
- Simplified HTML structure
- Added logo height constraint

### 3. `gestion/templates/gestion/login.html`
**Changes**:
- Added link to `main.css`
- Replaced dark background (`#1a1a2e`) with warm light (`#fafaf8`)
- New card design: flat, subtle border, no heavy shadow
- New button style: accent color, subtle hover
- Removed inline `<style>` block
- Cleaner form layout

### 4. `gestion/templates/gestion/dashboard.html`
**Changes**:
- Replaced Bootstrap row/col with CSS Grid (`dashboard-kpis`, `dashboard-charts`, `dashboard-actions`)
- Replaced colored KPI cards with new `kpi-card` component
- Updated period picker styles to use CSS variables
- Replaced Bootstrap card headers with clean design
- New action cards with icon + text layout
- Updated chart colors to match new palette
- Removed emojis from section titles

### 5. `gestion/templates/gestion/ventas_list.html`
**Changes**:
- Added section header with title and button
- Replaced colored KPI cards with `kpi-card` component
- Updated table styles (cleaner thead, subtle borders)
- Removed emojis from badges and titles
- Updated badge colors to new palette

### 6. `gestion/templates/gestion/clientes_list.html`
**Changes**:
- Added section header with title and button
- Updated search form with new input group styles
- Updated table styles
- Removed emojis from buttons
- Updated delete button icon

### 7. `gestion/templates/gestion/cotizaciones_list.html`
**Changes**:
- Added section header with title and button
- Updated table styles
- Removed emojis from section title
- Updated badge colors

## Color Palette

### Primary Colors
- `--clr-bg`: #fafaf8 (warm white)
- `--clr-surface`: #ffffff (pure white)
- `--clr-surface-alt`: #f5f5f0 (warm gray)
- `--clr-border`: #e8e6e1 (warm border)
- `--clr-text`: #1a1814 (dark warm)
- `--clr-text-secondary`: #6b6560 (medium warm)
- `--clr-text-muted`: #9c9590 (light warm)
- `--clr-accent`: #2d2a26 (dark accent)

### Functional Colors
- `--clr-success`: #2d6a4f (muted green)
- `--clr-warning`: #bc6c25 (muted amber)
- `--clr-danger`: #9b2226 (muted red)
- `--clr-info`: #457b9d (muted blue)

## Typography

### Fonts
- **Headings**: DM Serif Display (editorial serif)
- **Body**: Outfit (geometric sans)

### Font Sizes
- H1: 2.5rem
- H2: 2rem
- H3: 1.5rem
- H4: 1.25rem
- Body: 1rem
- Small: 0.875rem
- Tiny: 0.75rem

## Components

### KPI Card
Flat card with subtle border, hover effect with color accent line.

### Action Card
Link card with icon + text layout, hover effect with border color change.

### Bento Grid
CSS Grid system with responsive breakpoints:
- Default: auto-fit minmax(280px, 1fr)
- 2 columns: repeat(2, 1fr)
- 3 columns: repeat(3, 1fr)
- 4 columns: repeat(4, 1fr)
- 6 columns: repeat(6, 1fr)

## Responsive Breakpoints
- Mobile: < 768px (single column, smaller fonts)
- Tablet: 769px - 1024px (2-3 columns)
- Desktop: > 1024px (full grid)

## Files NOT Modified (Initial Redesign)
- `core/settings.py` - No settings changes
- `requirements.txt` - No dependency changes

## Backup Location
Full project backup: `/home/yonann/Descargas/ACRYLITEC_BACKUP_20260703_193837/`

---

# Context: Inventory Module - Products with Fixed Prices

## Overview
Changed the "Inventario" module from managing **Materiales** (raw acrylic sheets) to managing **Productos con precio fijo** (products with fixed prices). The module now shows products that have a `precio_fijo` defined, with stock management capabilities.

## Changes Made

### 1. `gestion/models.py`
**Added fields to `Productos` model:**
```python
stock_actual = models.IntegerField(default=0, verbose_name="Stock Actual")
stock_minimo = models.IntegerField(default=0, verbose_name="Stock Mínimo")
```

### 2. `gestion/views.py`
**New views added:**
- `inventario_productos(request)`: Lists products with `precio_fijo` defined, shows stock status
- `editar_stock_producto(request, pk)`: Form to edit stock_actual and stock_minimo

### 3. `gestion/urls.py`
**New routes added:**
```python
path('inventario/', views.inventario_productos, name='inventario_productos'),
path('inventario/<int:pk>/stock/', views.editar_stock_producto, name='editar_stock_producto'),
```

### 4. `gestion/templates/gestion/inventario_list.html` (NEW)
**Features:**
- Table showing: Foto, Nombre, Descripción, Stock Actual, Stock Mínimo, Precio Fijo, Acciones
- Alert for products with low stock
- Search functionality
- Color-coded stock status (green/orange/red)
- Default image placeholder when no photo

### 5. `gestion/templates/gestion/editar_stock.html` (NEW)
**Features:**
- Shows product info (name, description, price, photo)
- Form with stock_actual and stock_minimo fields
- Warning alert when stock is at or below minimum

### 6. `gestion/templates/gestion/base.html`
**Navigation updated:**
- Changed "Inventario" link from `lista_materiales` to `inventario_productos`
- Updated icon from `bi-boxes` to `bi-box-seam`

### 7. Database Migration
**Created:** `gestion/migrations/0009_productos_stock_actual_productos_stock_minimo.py`
- Adds `stock_actual` field (default=0)
- Adds `stock_minimo` field (default=0)

## URL Routes

| URL | View | Name | Description |
|-----|------|------|-------------|
| `/inventario/` | `inventario_productos` | `inventario_productos` | List products with fixed prices |
| `/inventario/<pk>/stock/` | `editar_stock_producto` | `editar_stock_producto` | Edit product stock |

## Stock Status Logic

| Condition | Badge | Row Color |
|-----------|-------|-----------|
| `stock_actual == 0` | "Sin stock" (red) | `table-warning` |
| `stock_actual <= stock_minimo` | "Stock bajo" (orange) | `table-warning` |
| `stock_actual > stock_minimo` | None | Default |

## Files Modified Summary

| File | Action |
|------|--------|
| `gestion/models.py` | Added stock fields to Productos |
| `gestion/views.py` | Added inventario_productos, editar_stock_producto |
| `gestion/urls.py` | Added inventario routes |
| `gestion/templates/gestion/base.html` | Updated navigation |
| `gestion/templates/gestion/inventario_list.html` | Created |
| `gestion/templates/gestion/editar_stock.html` | Created |
| `gestion/migrations/0009_*.py` | Created |

## Notes
- The `Materiales` model and its views/urls are kept for backward compatibility
- Products without `precio_fijo` are not shown in the inventory module
- Stock defaults to 0 for all existing products after migration

## Next Steps
1. Test inventory module functionality
2. Verify stock editing works correctly
3. Test low stock warnings
4. Deploy to Railway and verify production