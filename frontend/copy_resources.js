/**
 * Copy Live2D Cubism Core + Resources to public/ for frontend build
 */
"use strict";
const fs = require('fs');

const publicResources = [
  {src: '../CubismSdkForWeb-5-r.4/Core', dst: './public/Core'},
  {src: '../CubismSdkForWeb-5-r.4/Samples/Resources', dst: './public/Resources'},
];

publicResources.forEach((e) => { if (fs.existsSync(e.dst)) fs.rmSync(e.dst, { recursive: true }); });
publicResources.forEach((e) => fs.cpSync(e.src, e.dst, { recursive: true }));
