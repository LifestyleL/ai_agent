/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */

import { LogLevel } from '@framework/live2dcubismframework';

/**
 * 示例应用中使用的常量
 */

// 画布宽度和高度的像素值，或动态屏幕尺寸（"自动"）。
export const CanvasSize: { width: number; height: number } | 'auto' = 'auto';

// 画布数量
export const CanvasNum = 1;

// 画面
export const ViewScale = 1.0;
export const ViewMaxScale = 2.0;
export const ViewMinScale = 0.8;

export const ViewLogicalLeft = -1.0;
export const ViewLogicalRight = 1.0;
export const ViewLogicalBottom = -1.0;
export const ViewLogicalTop = 1.0;

export const ViewLogicalMaxLeft = -2.0;
export const ViewLogicalMaxRight = 2.0;
export const ViewLogicalMaxBottom = -2.0;
export const ViewLogicalMaxTop = 2.0;

// 相对路径
export const ResourcesPath = './Resources/';

// 模型后方的背景图像文件
export const BackImageName = 'back_class_normal.png';

// 齿轮-右上角切换图标
export const GearImageName = 'icon_gear.png';

// 结束按钮
export const PowerImageName = 'CloseNormal.png';

// 模型定义 ---------------------------------------------
// 存放模型的目录名称数组
// 需保证目录名称与 model3.json 的文件名保持一致
export const ModelDir: string[] = [
  // 'Haru',
  'Hiyori'
  // ,
  // 'Mark',
  // 'Natori',
  // 'Rice',
  // 'Mao',
  // 'Wanko'
];
export const ModelDirSize: number = ModelDir.length;

// 结合外部定义文件（JSON）进行匹配
export const MotionGroupIdle = 'Idle'; // 闲置动作
export const MotionGroupTapBody = 'TapBody'; // 点击身体部位时

// 结合外部定义文件（JSON）进行匹配
export const HitAreaNameHead = 'Head';
export const HitAreaNameBody = 'Body';

// 动作优先级常数
export const PriorityNone = 0;
export const PriorityIdle = 1;
export const PriorityNormal = 2;
export const PriorityForce = 3;//姿势最高优先级

// MOC3 的完整性验证选项
export const MOCConsistencyValidationEnable = true;
// motion3.json 的完整性验证选项
export const MotionConsistencyValidationEnable = true;

// 调试日志的显示选项
export const DebugLogEnable = true;
export const DebugTouchLogEnable = false;

//设置框架输出日志的级别
export const CubismLoggingLevel: LogLevel = LogLevel.LogLevel_Verbose;

// 默认渲染目标尺寸
export const RenderTargetWidth = 1900;
export const RenderTargetHeight = 1000;
