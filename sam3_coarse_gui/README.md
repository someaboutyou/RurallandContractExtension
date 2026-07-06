# SAM3 Coarse GUI

This folder contains the first GUI prototype for coarse segmentation with SAM 3.1.

Current capabilities:

- Open one image or one folder of images
- Show the business-label to model-label mapping
- Use the mapped SAM prompt to run coarse segmentation on the currently selected image
- Display the original image and the mask overlay side by side

Current model dependencies:

- SAM 3 repo: `E:\Work\AIVerification\repos\sam3`
- SAM 3.1 checkpoint: `E:\Work\AIVerification\sam3.1\sam3.1_multiplex.pt`
- Conda env: `sam_depth_anything`

Launch example:

```powershell
D:\Programs\anaconda3\envs\sam_depth_anything\python.exe E:\Work\RurallandContractExtension\sam3_coarse_gui\app.py
```
