/** AI 面部参数目标值 */
export interface AIFaceParams {
  ParamMouthOpenY?: number;
  ParamEyeLOpen?: number;
  ParamEyeROpen?: number;
  ParamAngleX?: number;
  ParamAngleY?: number;
  ParamAngleZ?: number;
  ParamBodyAngleX?: number;
  ParamBodyAngleY?: number;
  ParamBodyAngleZ?: number;
  ParamAllX?: number;
  ParamWaistAngleZ?: number;
  ParamLeftShoulderUp?: number;
  ParamRightShoulderUp?: number;
  ParamArmAL01?: number;
  ParamArmAR01?: number;
  ParamArmLA?: number;
  ParamArmRA?: number;
  ParamArmLB?: number;
  ParamArmRB?: number;
  ParamBrowLY?: number;
  ParamBrowRY?: number;
  ParamEyeBallX?: number;
  ParamEyeBallY?: number;
  ParamMouthForm?: number;
  ParamCheek?: number;
  ParamEyeLSmile?: number;
  ParamEyeRSmile?: number;
  mouth?: number;
  [key: string]: number | undefined;
}

/** 对话行 */
export interface DialogLine {
  text: string;
  type: 'ai' | 'user' | 'thinking';
}

/** Viseme 帧 */
export interface VisemeFrame {
  t: number;
  v: number | { aa: number; ih?: number; ou?: number; ee?: number; oh?: number };
}

/** 字幕状态 */
export interface SubtitleState {
  text: string;
  progress: number;
}

/** 记忆卡片 */
export interface MemoryCard {
  id: string;
  content: string;
  tags: string[];
  timestamp: number;
}

/** 日记条目 */
export interface DiaryEntry {
  id: string;
  date: string;
  summary: string;
  mood: string;
}

/** 设置画像类型 */
export type ProfileType = 'social' | 'busy' | 'auto' | 'quiet';

/** 用户设置 */
export interface UserProfile {
  type: ProfileType;
  frequency: number;
  followUp: number;
  nightMode: boolean;
}
