/**
 * Copyright(c) Live2D Inc. All rights reserved.
 *
 * Use of this source code is governed by the Live2D Open Software license
 * that can be found at https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html.
 */
import { AiAudioManager } from './ai/AiAudioManager';
import { CubismDefaultParameterId } from '@framework/cubismdefaultparameterid';
import { CubismModelSettingJson } from '@framework/cubismmodelsettingjson';
import {
  BreathParameterData,
  CubismBreath
} from '@framework/effect/cubismbreath';
import { CubismEyeBlink } from '@framework/effect/cubismeyeblink';
import { ICubismModelSetting } from '@framework/icubismmodelsetting';
import { CubismIdHandle } from '@framework/id/cubismid';
import { CubismFramework } from '@framework/live2dcubismframework';
import { CubismMatrix44 } from '@framework/math/cubismmatrix44';
import { CubismUserModel } from '@framework/model/cubismusermodel';
import {
  ACubismMotion,
  BeganMotionCallback,
  FinishedMotionCallback
} from '@framework/motion/acubismmotion';
import { CubismMotion } from '@framework/motion/cubismmotion';
import {
  CubismMotionQueueEntryHandle,
  InvalidMotionQueueEntryHandleValue
} from '@framework/motion/cubismmotionqueuemanager';
import { csmMap } from '@framework/type/csmmap';
import { csmRect } from '@framework/type/csmrectf';
import { csmString } from '@framework/type/csmstring';
import { csmVector } from '@framework/type/csmvector';
import {
  CSM_ASSERT,
  CubismLogError,
  CubismLogInfo
} from '@framework/utils/cubismdebug';

import * as LAppDefine from './lappdefine';
import { LAppPal } from './lapppal';
import { TextureInfo } from './lapptexturemanager';
import { LAppWavFileHandler } from './lappwavfilehandler';
import { CubismMoc } from '@framework/model/cubismmoc';
import { LAppDelegate } from './lappdelegate';
import { LAppSubdelegate } from './lappsubdelegate';
import { AI_WS } from './ai/AiWebSocket';
import { AI_IDLE } from './ai/AiIdleAnimator';
import { MICRO_EXPRESSION } from './ai/AiMicroNoise';

interface AIFaceParams {
  [key: string]: number;
  ParamEyeLOpen: number;
  ParamEyeROpen: number;
  ParamMouthOpenY: number;
  ParamAngleX: number;
  ParamAngleY: number;
  ParamAngleZ: number;
  ParamHairAhoge: number;
  ParamBodyAngleX: number;
  ParamBodyAngleY: number;
  ParamBodyAngleZ: number;
  PartArmA: number;        // 旧版兼容
  PartArmB: number;        // 旧版兼容
  ParamArmLA: number;      // 左腕 A
  ParamArmRA: number;      // 右腕 A
  ParamArmLB: number;      // 左腕 B
  ParamArmRB: number;      // 右腕 B
}

enum LoadStep {
  LoadAssets,
  LoadModel,
  WaitLoadModel,
  LoadExpression,
  WaitLoadExpression,
  LoadPhysics,
  WaitLoadPhysics,
  LoadPose,
  WaitLoadPose,
  SetupEyeBlink,
  SetupBreath,
  LoadUserData,
  WaitLoadUserData,
  SetupEyeBlinkIds,
  SetupLipSyncIds,
  SetupLayout,
  LoadMotion,
  WaitLoadMotion,
  CompleteInitialize,
  CompleteSetupModel,
  LoadTexture,
  WaitLoadTexture,
  CompleteSetup
}

/**
 * ユーザーが実際に使用するモデルの実装クラス<br>
 * モデル生成、機能コンポーネント生成、更新処理とレンダリングの呼び出しを行う。
 */
export class LAppModel extends CubismUserModel {


  // ------------------------------
// AI 平滑控制（和原生眨眼 SAME 流畅度）
// ------------------------------
  private _smoothedAI: AIFaceParams = {
    ParamEyeLOpen: 1.0,    // 左眼开合
    ParamEyeROpen: 1.0,    // 右眼开合
    ParamMouthOpenY: 0.0,  // 嘴巴开合（模型原生唯一嘴部开合参数）
    ParamAngleX: 0.0,      // 头部左右转
    ParamAngleY: 0.0,
    ParamAngleZ: 0.0,     // 头部上下仰
    ParamHairAhoge: 0.0,   // 头发/呆毛飘动（核心头发参数）
    ParamBodyAngleX: 0.0,  // 身体左右摇摆（核心身体参数）
    ParamBodyAngleY: 0.0,  // 身体上下俯仰
    ParamBodyAngleZ: 0.0,  // 身体轻微歪转（增强自然度）
    PartArmA: 1,           // 旧版兼容
    PartArmB: 1,           // 旧版兼容
    ParamArmLA: 1.0,       // 左腕 A（实际模型参数）
    ParamArmRA: 1.0,       // 右腕 A（实际模型参数）
    ParamArmLB: 1.0,       // 左腕 B（实际模型参数）
    ParamArmRB: 1.0,       // 右腕 B（实际模型参数）
  };

  // 类的成员变量
  private _blinkTimer: number = 0;       // 当前眨眼倒计时
  private _blinkDuration: number = 0.25; // 一次眨眼总时长，单位秒
  private _lastTarget: any = {}; // 🌟 外推预判用的上一帧缓存



  private _damping = 0.78;           // 阻尼系数（0.75~0.85，越低拖尾越明显）
  //private _velocity: { [key: string]: number } = {};   // 速度缓存-›废除
  /**
   * model3.jsonが置かれたディレクトリとファイルパスからモデルを生成する
   * @param dir
   * @param fileName
   */
  public loadAssets(dir: string, fileName: string): void {
    this._modelHomeDir = dir;

    fetch(`${this._modelHomeDir}${fileName}`)
      .then(response => response.arrayBuffer())
      .then(arrayBuffer => {
        const setting: ICubismModelSetting = new CubismModelSettingJson(
          arrayBuffer,
          arrayBuffer.byteLength
        );

        // ステートを更新
        this._state = LoadStep.LoadModel;

        // 結果を保存
        this.setupModel(setting);
      })
      .catch(error => {
        // model3.json読み込みでエラーが発生した時点で描画は不可能なので、setupせずエラーをcatchして何もしない
        CubismLogError(`Failed to load file ${this._modelHomeDir}${fileName}`);
      });
  }
 
  /**
   * model3.jsonからモデルを生成する。
   * model3.jsonの記述に従ってモデル生成、モーション、物理演算などのコンポーネント生成を行う。
   *
   * @param setting ICubismModelSettingのインスタンス
   */
  private setupModel(setting: ICubismModelSetting): void {
    this._updating = true;
    this._initialized = false;

    this._modelSetting = setting;

    // CubismModel
    if (this._modelSetting.getModelFileName() != '') {
      const modelFileName = this._modelSetting.getModelFileName();

      fetch(`${this._modelHomeDir}${modelFileName}`)
        .then(response => {
          if (response.ok) {
            return response.arrayBuffer();
          } else if (response.status >= 400) {
            CubismLogError(
              `Failed to load file ${this._modelHomeDir}${modelFileName}`
            );
            return new ArrayBuffer(0);
          }
        })
        .then(arrayBuffer => {
          this.loadModel(arrayBuffer, this._mocConsistency);
          this._state = LoadStep.LoadExpression;

          // callback
          loadCubismExpression();
        });

      this._state = LoadStep.WaitLoadModel;
    } else {
      LAppPal.printMessage('Model data does not exist.');
    }

    // Expression
    const loadCubismExpression = (): void => {
      if (this._modelSetting.getExpressionCount() > 0) {
        const count: number = this._modelSetting.getExpressionCount();

        for (let i = 0; i < count; i++) {
          const expressionName = this._modelSetting.getExpressionName(i);
          const expressionFileName =
            this._modelSetting.getExpressionFileName(i);

          fetch(`${this._modelHomeDir}${expressionFileName}`)
            .then(response => {
              if (response.ok) {
                return response.arrayBuffer();
              } else if (response.status >= 400) {
                CubismLogError(
                  `Failed to load file ${this._modelHomeDir}${expressionFileName}`
                );
                // ファイルが存在しなくてもresponseはnullを返却しないため、空のArrayBufferで対応する
                return new ArrayBuffer(0);
              }
            })
            .then(arrayBuffer => {
              const motion: ACubismMotion = this.loadExpression(
                arrayBuffer,
                arrayBuffer.byteLength,
                expressionName
              );

              if (this._expressions.getValue(expressionName) != null) {
                ACubismMotion.delete(
                  this._expressions.getValue(expressionName)
                );
                this._expressions.setValue(expressionName, null);
              }

              this._expressions.setValue(expressionName, motion);

              this._expressionCount++;

              if (this._expressionCount >= count) {
                this._state = LoadStep.LoadPhysics;

                // callback
                loadCubismPhysics();
              }
            });
        }
        this._state = LoadStep.WaitLoadExpression;
      } else {
        this._state = LoadStep.LoadPhysics;

        // callback
        loadCubismPhysics();
      }
    };

    // Physics
    const loadCubismPhysics = (): void => {
      if (this._modelSetting.getPhysicsFileName() != '') {
        const physicsFileName = this._modelSetting.getPhysicsFileName();

        fetch(`${this._modelHomeDir}${physicsFileName}`)
          .then(response => {
            if (response.ok) {
              return response.arrayBuffer();
            } else if (response.status >= 400) {
              CubismLogError(
                `Failed to load file ${this._modelHomeDir}${physicsFileName}`
              );
              return new ArrayBuffer(0);
            }
          })
          .then(arrayBuffer => {
            this.loadPhysics(arrayBuffer, arrayBuffer.byteLength);

            this._state = LoadStep.LoadPose;

            // callback
            loadCubismPose();
          });
        this._state = LoadStep.WaitLoadPhysics;
      } else {
        this._state = LoadStep.LoadPose;

        // callback
        loadCubismPose();
      }
    };

    // Pose
    const loadCubismPose = (): void => {
      if (this._modelSetting.getPoseFileName() != '') {
        const poseFileName = this._modelSetting.getPoseFileName();

        fetch(`${this._modelHomeDir}${poseFileName}`)
          .then(response => {
            if (response.ok) {
              return response.arrayBuffer();
            } else if (response.status >= 400) {
              CubismLogError(
                `Failed to load file ${this._modelHomeDir}${poseFileName}`
              );
              return new ArrayBuffer(0);
            }
          })
          .then(arrayBuffer => {
            this.loadPose(arrayBuffer, arrayBuffer.byteLength);

            this._state = LoadStep.SetupEyeBlink;

            // callback
            setupEyeBlink();
          });
        this._state = LoadStep.WaitLoadPose;
      } else {
        this._state = LoadStep.SetupEyeBlink;

        // callback
        setupEyeBlink();
      }
    };

    // EyeBlink
    const setupEyeBlink = (): void => {
      if (this._modelSetting.getEyeBlinkParameterCount() > 0) {
        this._eyeBlink = CubismEyeBlink.create(this._modelSetting);
        this._state = LoadStep.SetupBreath;
      }

      // callback
      setupBreath();
    };

    // Breath
    const setupBreath = (): void => {
      this._breath = CubismBreath.create();

      const breathParameters: csmVector<BreathParameterData> = new csmVector();
      breathParameters.pushBack(
        new BreathParameterData(this._idParamAngleX, 0.0, 15.0, 6.5345, 0.5)
      );
      breathParameters.pushBack(
        new BreathParameterData(this._idParamAngleY, 0.0, 8.0, 3.5345, 0.5)
      );
      breathParameters.pushBack(
        new BreathParameterData(this._idParamAngleZ, 0.0, 10.0, 5.5345, 0.5)
      );
      breathParameters.pushBack(
        new BreathParameterData(this._idParamBodyAngleX, 0.0, 4.0, 15.5345, 0.5)
      );
      breathParameters.pushBack(
        new BreathParameterData(
          CubismFramework.getIdManager().getId(
            CubismDefaultParameterId.ParamBreath
          ),
          0.5,
          0.5,
          3.2345,
          1
        )
      );

      this._breath.setParameters(breathParameters);
      this._state = LoadStep.LoadUserData;

      // callback
      loadUserData();
    };

    // UserData
    const loadUserData = (): void => {
      if (this._modelSetting.getUserDataFile() != '') {
        const userDataFile = this._modelSetting.getUserDataFile();

        fetch(`${this._modelHomeDir}${userDataFile}`)
          .then(response => {
            if (response.ok) {
              return response.arrayBuffer();
            } else if (response.status >= 400) {
              CubismLogError(
                `Failed to load file ${this._modelHomeDir}${userDataFile}`
              );
              return new ArrayBuffer(0);
            }
          })
          .then(arrayBuffer => {
            this.loadUserData(arrayBuffer, arrayBuffer.byteLength);

            this._state = LoadStep.SetupEyeBlinkIds;

            // callback
            setupEyeBlinkIds();
          });

        this._state = LoadStep.WaitLoadUserData;
      } else {
        this._state = LoadStep.SetupEyeBlinkIds;

        // callback
        setupEyeBlinkIds();
      }
    };

    // EyeBlinkIds
    const setupEyeBlinkIds = (): void => {
      const eyeBlinkIdCount: number =
        this._modelSetting.getEyeBlinkParameterCount();

      for (let i = 0; i < eyeBlinkIdCount; ++i) {
        this._eyeBlinkIds.pushBack(
          this._modelSetting.getEyeBlinkParameterId(i)
        );
      }

      this._state = LoadStep.SetupLipSyncIds;

      // callback
      setupLipSyncIds();
    };

    // LipSyncIds
    const setupLipSyncIds = (): void => {
      const lipSyncIdCount = this._modelSetting.getLipSyncParameterCount();

      for (let i = 0; i < lipSyncIdCount; ++i) {
        this._lipSyncIds.pushBack(this._modelSetting.getLipSyncParameterId(i));
      }
      this._state = LoadStep.SetupLayout;

      // callback
      setupLayout();
    };

    // Layout
    const setupLayout = (): void => {
      const layout: csmMap<string, number> = new csmMap<string, number>();

      if (this._modelSetting == null || this._modelMatrix == null) {
        CubismLogError('Failed to setupLayout().');
        return;
      }

      this._modelSetting.getLayoutMap(layout);
      this._modelMatrix.setupFromLayout(layout);
      this._state = LoadStep.LoadMotion;

      // callback
      loadCubismMotion();
    };

    // Motion
    const loadCubismMotion = (): void => {
      this._state = LoadStep.WaitLoadMotion;
      this._model.saveParameters();
      this._allMotionCount = 0;
      this._motionCount = 0;
      const group: string[] = [];

      const motionGroupCount: number = this._modelSetting.getMotionGroupCount();

      // 求动作的总数
      for (let i = 0; i < motionGroupCount; i++) {
        group[i] = this._modelSetting.getMotionGroupName(i);
        this._allMotionCount += this._modelSetting.getMotionCount(group[i]);
      }

      // 动作加载
      for (let i = 0; i < motionGroupCount; i++) {
        this.preLoadMotionGroup(group[i]);
      }

      // 无动作时
      if (motionGroupCount == 0) {
        this._state = LoadStep.LoadTexture;

        // 停止所有动作
        this._motionManager.stopAllMotions();

        this._updating = false;
        this._initialized = true;

        this.createRenderer();
        this.setupTextures();
        this.getRenderer().startUp(this._subdelegate.getGlManager().getGl());
      }
    };
  }

  /**
   * 向纹理单元加载纹理
   */
  private setupTextures(): void {
    // 为提升 iPhone 端的画质表现，在 TypeScript 中采用预乘透明度（premultipliedAlpha）方案
    const usePremultiply = true;

    if (this._state == LoadStep.LoadTexture) {
      // 用于纹理加载
      const textureCount: number = this._modelSetting.getTextureCount();

      for (
        let modelTextureNumber = 0;
        modelTextureNumber < textureCount;
        modelTextureNumber++
      ) {
        // 纹理名称为空字符串时，跳过加载与绑定处理
        if (this._modelSetting.getTextureFileName(modelTextureNumber) == '') {
          console.log('getTextureFileName null');
          continue;
        }

        // 向 WebGL 的纹理单元加载纹理
        let texturePath =
          this._modelSetting.getTextureFileName(modelTextureNumber);
        texturePath = this._modelHomeDir + texturePath;

        // 加载完成时调用的回调函数
        const onLoad = (textureInfo: TextureInfo): void => {
          this.getRenderer().bindTexture(modelTextureNumber, textureInfo.id);

          this._textureCount++;

          if (this._textureCount >= textureCount) {
            // 加载完成
            this._state = LoadStep.CompleteSetup;
          }
        };

        //读取加载
        this._subdelegate
          .getTextureManager()
          .createTextureFromPngFile(texturePath, usePremultiply, onLoad);
        this.getRenderer().setIsPremultipliedAlpha(usePremultiply);
      }

      this._state = LoadStep.WaitLoadTexture;
    }
  }




  public update(): void {
    if (this._state != LoadStep.CompleteSetup) return;

    const dt = Math.min(LAppPal.getDeltaTime(), 0.1);
    this._userTimeSeconds += dt;

    this._model.loadParameters();

    // ==========================================
    // 王者归来：官方引擎全家桶全权接管身体和五官
    // ==========================================
    if (this._motionManager != null) this._motionManager.updateMotion(this._model, dt); // 动作轮播
    if (this._physics != null) this._physics.evaluate(this._model, dt);                 // 物理飘动
    if (this._pose != null) this._pose.updateParameters(this._model, dt);               // 骨骼防穿模
    if (this._breath != null) this._breath.updateParameters(this._model, dt);           // 呼吸起伏

    // ==========================================
    // AI 空闲动画（后端未控制时让模型自主微动）
    // ==========================================
    AI_IDLE.update(dt);

    const idManager = CubismFramework.getIdManager();
    const target = AI_WS.aiFaceParams as Record<string, any>;
    const touched = AI_WS.backendTouched;

    // ── Layer 0: 微表情噪声（"活气系统"）—— 极小幅连续随机游走 ──
    const microOffsets = MICRO_EXPRESSION.apply(dt, touched);
    for (const paramId of Object.keys(microOffsets)) {
      const id = idManager.getId(paramId);
      if (id) this._model.setParameterValueById(id, microOffsets[paramId]);
    }

    // ── AI 参数注入：只设原始目标值，SDK physics 负责平滑过渡 ──
    // AiIdleAnimator 已写入 head/body 正弦值，这里直接 apply

    // Mouth — TTS 口型同步优先，后端参数覆盖次之
    const audioMgr = AiAudioManager.getInstance();
    audioMgr.updateViseme();
    const isPlayingAudio = audioMgr.getIsPlaying();
    const mb = target["ParamMouthOpenY"];
    const backendMouth = (mb !== undefined && mb !== null);

    if (isPlayingAudio) {
      // TTS 播放中：viseme 数据驱动口型，×1.4 放大张嘴幅度
      const visemeMouth = Math.min(1.0, audioMgr.currentViseme.aa * 1.4);
      const lerpMouth = 1 - Math.exp(-20.0 * dt);
      this._smoothedAI.ParamMouthOpenY += (visemeMouth - this._smoothedAI.ParamMouthOpenY) * lerpMouth;
    } else if (backendMouth) {
      // 后端显式控制口型（无 TTS 时）
      const lerpMouth = 1 - Math.exp(-20.0 * dt);
      this._smoothedAI.ParamMouthOpenY += (mb - this._smoothedAI.ParamMouthOpenY) * lerpMouth;
    } else {
      // 静默时平滑闭口
      this._smoothedAI.ParamMouthOpenY *= Math.exp(-8.0 * dt);
    }
    this._model.setParameterValueById(idManager.getId("ParamMouthOpenY"), this._smoothedAI.ParamMouthOpenY);

    // Head / Body — 轻量 lerp（head 无 physics 挂载，需手动平滑，factor=3 约 1s 收敛）
    const lerpGentle = 1 - Math.exp(-3.0 * dt);
    for (const key of ["ParamAngleX", "ParamAngleY", "ParamAngleZ",
                        "ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ",
                        "ParamAllX", "ParamWaistAngleZ",
                        "ParamLeftShoulderUp", "ParamRightShoulderUp"]) {
      const id = idManager.getId(key);
      if (!id) continue;
      const val = target[key];
      if (val !== undefined && val !== null) {
        const cur = (this._smoothedAI as any)[key] || 0;
        (this._smoothedAI as any)[key] = cur + (val - cur) * lerpGentle;
        this._model.setParameterValueById(id, (this._smoothedAI as any)[key]);
      }
    }
    // Hair — 直接设，.physics3.json 负责头发飘动
    const idHair = idManager.getId("ParamHairAhoge");
    if (idHair && target["ParamHairAhoge"] !== undefined) {
      this._model.setParameterValueById(idHair, target["ParamHairAhoge"]);
    }

    // Eye blink — SDK 眨眼计时器优先，后端显式下发时覆盖
    const idEyeL = idManager.getId("ParamEyeLOpen");
    const idEyeR = idManager.getId("ParamEyeROpen");
    if (idEyeL && idEyeR) {
      let blink = 1.0;
      if (this._blinkTimer > 0) {
        this._blinkTimer -= dt;
        blink = Math.sin((1 - this._blinkTimer / this._blinkDuration) * Math.PI);
      } else if (Math.random() < 0.004) {
        this._blinkDuration = 0.25;
        this._blinkTimer = this._blinkDuration;
      }
      const backendEye = touched.has("ParamEyeLOpen");
      const eL = backendEye ? (target["ParamEyeLOpen"] ?? blink) : blink;
      const eR = backendEye ? (target["ParamEyeROpen"] ?? blink) : blink;
      this._model.setParameterValueById(idEyeL, eL);
      this._model.setParameterValueById(idEyeR, eR);
    }

    // Arm / Shoulder params — 空闲动画/后端均可驱动，有值就 apply
    // ParamArmAL01/AR01 是 Natori 真实肩部旋转参数
    for (const key of ["ParamArmAL01", "ParamArmAR01", "ParamArmLA", "ParamArmRA", "ParamArmLB", "ParamArmRB"]) {
      const id = idManager.getId(key);
      if (!id) continue;
      const val = target[key];
      if (val !== undefined && val !== null) {
        const cur = (this._smoothedAI as any)[key] || 1.0;
        (this._smoothedAI as any)[key] = cur + (val - cur) * lerpGentle;
        this._model.setParameterValueById(id, (this._smoothedAI as any)[key]);
      }
    }

    // Consume command queues from AI_WS
    if (AI_WS.expressionQueue.length > 0) {
      this.setExpression(AI_WS.expressionQueue.shift()!);
    }
    if (AI_WS.motionQueue.length > 0) {
      const m = AI_WS.motionQueue.shift()!;
      const prio = m.group === 'Idle' ? LAppDefine.PriorityIdle : LAppDefine.PriorityNormal;
      const onFinish = m.group === 'Idle' ? AI_IDLE.onIdleFinished : undefined;
      this.startRandomMotion(m.group, prio, onFinish);
    }

    this._model.saveParameters();
    this._model.update();
  }
















  /**
   *重新构建渲染器
   */
  // public reloadRenderer(): void {
  //   this.deleteRenderer();
  //   this.createRenderer();
  //   this.setupTextures();
  // }

  /**
   * 更新
   */
//     public update(): void {
//     if (this._state != LoadStep.CompleteSetup) return;

//     // 调试：输出所有参数ID（只执行一次）- 这段保留没问题
//     if (this._model && !(window as any)._paramsLogged) {
//       try {
//         const paramCount = this._model.getParameterCount();
//         console.log(`[MODEL-DEBUG] 模型共有 ${paramCount} 个参数:`);
//         for (let i = 0; i < Math.min(paramCount, 50); i++) {
//           const paramId = this._model.getParameterId(i);
//           const paramValue = this._model.getParameterValueById(paramId);
//           const paramStr = JSON.stringify(paramId);
//           console.log(`  [${i}] ${paramStr}: ${paramValue.toFixed(3)}`);
//         }
//         if (paramCount > 50) console.log(`[MODEL-DEBUG] ... 还有 ${paramCount - 50} 个参数未显示`);
//         (window as any)._paramsLogged = true;
//       } catch (e) {
//         console.error("[MODEL-DEBUG] 获取参数失败:", e);
//       }
//     }

//     const deltaTimeSeconds: number = LAppPal.getDeltaTime();
//     // 防止 deltaTime 异常（比如切出标签页再切回来变成好几秒）

//     const dt = Math.min(deltaTimeSeconds, 0.1); 
//     this._userTimeSeconds += dt;

//     this._dragManager.update(dt);
//     this._dragX = this._dragManager.getX();
//     this._dragY = this._dragManager.getY();

//     // ==========================================
//     // 1. 恢复模型底层的原始状态
//     // ==========================================
//     this._model.loadParameters(); 
//     // this._motionManager.updateMotion(this._model, dt); // 屏蔽待机动作，防止覆盖 AI 参数
//     // if (this._expressionManager != null) this._expressionManager.updateMotion(this._model, dt); // 屏蔽默认表情锁死参数

//     if (this._physics != null) this._physics.evaluate(this._model, dt);
//     if (this._pose != null) this._pose.updateParameters(this._model, dt);
//     if (this._breath != null) this._breath.updateParameters(this._model, dt);

//     // ==========================================
//     // 2. AI 参数平滑处理 (引入 deltaTime)
//     // ==========================================
//     // const idManager = CubismFramework.getIdManager();
//     const target = AI_WS.aiFaceParams as AIFaceParams;
//     const audioMgr = LAppAudioManager.getInstance();

//     if (!this._smoothedAI) this._smoothedAI = { ...target }; 
//     if (!this._blinkTimer) this._blinkTimer = 0;

//     // 🌟 核心：基于时间的指数衰减平滑算法
//     // lerpFactor 越大跟得越快。10.0 表示约0.2秒到位，适合头部；5.0表示约0.4秒到位，适合身体
//     const lerpFactorHead = 1 - Math.exp(-10.0 * dt); 
//     const lerpFactorBody = 1 - Math.exp(-5.0 * dt);

//     ["ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamHairAhoge"].forEach(key => {
//       const current = this._smoothedAI[key] || 0;
//       const targetVal = target[key] || 0;
//       this._smoothedAI[key] = current + (targetVal - current) * lerpFactorHead;
//     });

//     ["ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ"].forEach(key => {
//       const current = this._smoothedAI[key] || 0;
//       const targetVal = target[key] || 0;
//       this._smoothedAI[key] = current + (targetVal - current) * lerpFactorBody;
//     });

//     // 手臂参数 (直接使用，不平滑)
//     const armKeys = ["ParamArmLA", "ParamArmRA", "ParamArmLB", "ParamArmRB"];
//     armKeys.forEach(key => {
//       if (target[key] !== undefined && target[key] !== null) {
//         this._smoothedAI[key] = target[key];
//       }
//     });

//     // 兼容旧的PartArmA/B
//     if (target.PartArmA !== undefined && target.PartArmA !== null) {
//       this._smoothedAI.ParamArmLA = target.PartArmA;
//       this._smoothedAI.ParamArmLB = target.PartArmA;
//     }
//     if (target.PartArmB !== undefined && target.PartArmB !== null) {
//       this._smoothedAI.ParamArmRA = target.PartArmB;
//       this._smoothedAI.ParamArmRB = target.PartArmB;
//     }

//     // 🌟 嘴巴处理
//     audioMgr.updateViseme();
//     if (audioMgr.getIsPlaying()) {
//       this._smoothedAI.ParamMouthOpenY = Math.max(
//         audioMgr.currentViseme.aa, audioMgr.currentViseme.ou, audioMgr.currentViseme.oh
//       );
//     } else {
//       if (target.ParamMouthOpenY !== undefined && target.ParamMouthOpenY !== null) {
//         const current = this._smoothedAI.ParamMouthOpenY || 0;
//         // 嘴巴用稍慢一点的平滑
//         this._smoothedAI.ParamMouthOpenY = current + (target.ParamMouthOpenY - current) * lerpFactorHead;
//       } else {
//         // 平滑回归闭嘴
//         this._smoothedAI.ParamMouthOpenY = (this._smoothedAI.ParamMouthOpenY || 0) * Math.exp(-8.0 * dt);
//       }
//     }

//     // 🌟 眨眼处理
//     let blink = 1.0;
//     if (this._blinkTimer > 0) {
//       this._blinkTimer -= dt;
//       const t = 1 - this._blinkTimer / this._blinkDuration;
//       blink = Math.sin(t * Math.PI);
//     } else if (Math.random() < 0.004) { // 随机眨眼概率
//       this._blinkDuration = 0.25;
//       this._blinkTimer = this._blinkDuration;
//     }

//     this._smoothedAI.ParamEyeLOpen = (target.ParamEyeLOpen !== undefined && target.ParamEyeLOpen !== null) 
//       ? target.ParamEyeLOpen : blink;
//     this._smoothedAI.ParamEyeROpen = (target.ParamEyeROpen !== undefined && target.ParamEyeROpen !== null) 
//       ? target.ParamEyeROpen : blink;

// // ==========================================
// // 3. 统一应用参数到模型
// // ==========================================

// const idManager = CubismFramework.getIdManager();

// // 直接获取 ID 并赋值（和 Math.sin 测试完全一样的方式）
// const idMouth = idManager.getId("ParamMouthOpenY");
// if (idMouth) this._model.setParameterValueById(idMouth, this._smoothedAI.ParamMouthOpenY);

// const idEyeL = idManager.getId("ParamEyeLOpen");
// if (idEyeL) this._model.setParameterValueById(idEyeL, this._smoothedAI.ParamEyeLOpen);

// const idEyeR = idManager.getId("ParamEyeROpen");
// if (idEyeR) this._model.setParameterValueById(idEyeR, this._smoothedAI.ParamEyeROpen);

// const idAngleX = idManager.getId("ParamAngleX");
// if (idAngleX) this._model.setParameterValueById(idAngleX, this._smoothedAI.ParamAngleX);

// const idAngleY = idManager.getId("ParamAngleY");
// if (idAngleY) this._model.setParameterValueById(idAngleY, this._smoothedAI.ParamAngleY);

// const idAngleZ = idManager.getId("ParamAngleZ");
// if (idAngleZ) this._model.setParameterValueById(idAngleZ, this._smoothedAI.ParamAngleZ);

// const idBodyX = idManager.getId("ParamBodyAngleX");
// if (idBodyX) this._model.setParameterValueById(idBodyX, this._smoothedAI.ParamBodyAngleX);

// const idBodyY = idManager.getId("ParamBodyAngleY");
// if (idBodyY) this._model.setParameterValueById(idBodyY, this._smoothedAI.ParamBodyAngleY);

// const idBodyZ = idManager.getId("ParamBodyAngleZ");
// if (idBodyZ) this._model.setParameterValueById(idBodyZ, this._smoothedAI.ParamBodyAngleZ);

// const idHair = idManager.getId("ParamHairAhoge");
// if (idHair) this._model.setParameterValueById(idHair, this._smoothedAI.ParamHairAhoge);

// const idArmLA = idManager.getId("ParamArmLA");
// if (idArmLA) this._model.setParameterValueById(idArmLA, this._smoothedAI.ParamArmLA);

// const idArmRA = idManager.getId("ParamArmRA");
// if (idArmRA) this._model.setParameterValueById(idArmRA, this._smoothedAI.ParamArmRA);

// const idArmLB = idManager.getId("ParamArmLB");
// if (idArmLB) this._model.setParameterValueById(idArmLB, this._smoothedAI.ParamArmLB);

// const idArmRB = idManager.getId("ParamArmRB");
// if (idArmRB) this._model.setParameterValueById(idArmRB, this._smoothedAI.ParamArmRB);
    
// // 🌟 鼠标拖拽叠加（也改用 getId）
// const idEyeBallX = idManager.getId("ParamEyeBallX");
// const idEyeBallY = idManager.getId("ParamEyeBallY");
// if (idAngleX) this._model.addParameterValueById(idAngleX, this._dragX * 30);
// if (idAngleY) this._model.addParameterValueById(idAngleY, this._dragY * 30);
// if (idAngleZ) this._model.addParameterValueById(idAngleZ, this._dragX * this._dragY * -30);
// if (idBodyX) this._model.addParameterValueById(idBodyX, this._dragX * 10);
// if (idEyeBallX) this._model.addParameterValueById(idEyeBallX, this._dragX);
// if (idEyeBallY) this._model.addParameterValueById(idEyeBallY, this._dragY);


// // 最终保存状态并刷新渲染
//     this._model.saveParameters(); 
//     this._model.update();
//   }



  /**
   *@param group 动作组名称
    *@param no 组内编号
    *@param priority 优先级
    *@param onFinishedMotionHandler 动作播放结束时调用的回调函数
    *@return 返回已启动动作的识别编号。该编号可作为判断单个动作是否结束的 isFinished () 方法的参数。无法启动时返回 [-1]
  */
    public startMotion(
    group: string,
    no: number,
    priority: number,
    onFinishedMotionHandler?: FinishedMotionCallback,
    onBeganMotionHandler?: BeganMotionCallback
  ): CubismMotionQueueEntryHandle {
    if (priority == LAppDefine.PriorityForce) {
      this._motionManager.setReservePriority(priority);
    } else if (!this._motionManager.reserveMotion(priority)) {
      if (this._debugMode) {
        LAppPal.printMessage("[APP]can't start motion.");
      }
      return InvalidMotionQueueEntryHandleValue;
    }

    const motionFileName = this._modelSetting!.getMotionFileName(group, no);

    // ex) idle_0
    const name = `${group}_${no}`;
    let motion: CubismMotion = this._motions.getValue(name) as CubismMotion;
    let autoDelete = false;

    if (motion == null) {
      fetch(`${this._modelHomeDir}${motionFileName}`)
        .then(response => {
          if (response.ok) {
            return response.arrayBuffer();
          } else if (response.status >= 400) {
            CubismLogError(
              `Failed to load file ${this._modelHomeDir}${motionFileName}`
            );
            return new ArrayBuffer(0);
          } else {
            // 其他错误情况（如重定向等）
            return new ArrayBuffer(0);
          }
        })
        .then(arrayBuffer => {
          motion = this.loadMotion(
            arrayBuffer,
            arrayBuffer.byteLength,
            name,
            onFinishedMotionHandler!,
            onBeganMotionHandler!,
            this._modelSetting!,
            group,
            no,
            this._motionConsistency
          );
        });

      if (motion) {
        motion.setEffectIds(this._eyeBlinkIds, this._lipSyncIds);
        autoDelete = true; // 終了時にメモリから削除
      } else {
        CubismLogError("Can't start motion {0} .", motionFileName);
        // ロードできなかったモーションのReservePriorityをリセットする
        this._motionManager.setReservePriority(LAppDefine.PriorityNone);
        return InvalidMotionQueueEntryHandleValue;
      }
    } else {
      motion.setBeganMotionHandler(onBeganMotionHandler);
      motion.setFinishedMotionHandler(onFinishedMotionHandler);
    }

    //voice
    const voice = this._modelSetting.getMotionSoundFileName(group, no);
    if (voice.localeCompare('') != 0) {
      let path = voice;
      path = this._modelHomeDir + path;
      this._wavFileHandler.start(path);
    }

    if (this._debugMode) {
      LAppPal.printMessage(`[APP]start motion: [${group}_${no}]`);
    }
    return this._motionManager.startMotionPriority(
      motion,
      autoDelete,
      priority
    );
  }

  /**
   * ランダムに選ばれたモーションの再生を開始する。
   * @param group モーショングループ名
   * @param priority 優先度
   * @param onFinishedMotionHandler モーション再生終了時に呼び出されるコールバック関数
   * @return 開始したモーションの識別番号を返す。個別のモーションが終了したか否かを判定するisFinished()の引数で使用する。開始できない時は[-1]
   */
  public startRandomMotion(
    group: string,
    priority: number,
    onFinishedMotionHandler?: FinishedMotionCallback,
    onBeganMotionHandler?: BeganMotionCallback
  ): CubismMotionQueueEntryHandle {
    if (this._modelSetting.getMotionCount(group) == 0) {
      return InvalidMotionQueueEntryHandleValue;
    }

    const no: number = Math.floor(
      Math.random() * this._modelSetting.getMotionCount(group)
    );

    return this.startMotion(
      group,
      no,
      priority,
      onFinishedMotionHandler,
      onBeganMotionHandler
    );
  }

  /**
   * 引数で指定した表情モーションをセットする
   *
   * @param expressionId 表情モーションのID
   */
  public setExpression(expressionId: string): void {
    const motion: ACubismMotion = this._expressions.getValue(expressionId);

    if (this._debugMode) {
      LAppPal.printMessage(`[APP]expression: [${expressionId}]`);
    }

    if (motion != null) {
      this._expressionManager.startMotion(motion, false);
    } else {
      if (this._debugMode) {
        LAppPal.printMessage(`[APP]expression[${expressionId}] is null`);
      }
    }
  }

  /**
   * 设置随机选中的表情动作
   */
  public setRandomExpression(): void {
    if (this._expressions.getSize() == 0) {
      return;
    }

    const no: number = Math.floor(Math.random() * this._expressions.getSize());

    for (let i = 0; i < this._expressions.getSize(); i++) {
      if (i == no) {
        const name: string = this._expressions._keyValues[i].first;
        this.setExpression(name);
        return;
      }
    }
  }

  /**
   * イベントの発火を受け取る
   */
  public motionEventFired(eventValue: csmString): void {
    CubismLogInfo('{0} is fired on LAppModel!!', eventValue.s);
  }

  /**
   * 当たり判定テスト
   * 从指定 ID 的顶点列表计算矩形，并判断坐标是否在矩形范围内。
   *
   * @param hitArenaName  当たり判定をテストする対象のID
   * @param x             判定を行うX座標
   * @param y             判定を行うY座標
   */
  public hitTest(hitArenaName: string, x: number, y: number): boolean {
    // 透明時は当たり判定無し。
    if (this._opacity < 1) {
      return false;
    }

    const count: number = this._modelSetting.getHitAreasCount();

    for (let i = 0; i < count; i++) {
      if (this._modelSetting.getHitAreaName(i) == hitArenaName) {
        const drawId: CubismIdHandle = this._modelSetting.getHitAreaId(i);
        return this.isHit(drawId, x, y);
      }
    }

    return false;
  }

  /**
   * モーションデータをグループ名から一括でロードする。
   * モーションデータの名前は内部でModelSettingから取得する。
   *
   * @param group モーションデータのグループ名
   */
  public preLoadMotionGroup(group: string): void {
    for (let i = 0; i < this._modelSetting.getMotionCount(group); i++) {
      const motionFileName = this._modelSetting.getMotionFileName(group, i);

      // ex) idle_0
      const name = `${group}_${i}`;
      if (this._debugMode) {
        LAppPal.printMessage(
          `[APP]load motion: ${motionFileName} => [${name}]`
        );
      }

      fetch(`${this._modelHomeDir}${motionFileName}`)
        .then(response => {
          if (response.ok) {
            return response.arrayBuffer();
          } else if (response.status >= 400) {
            CubismLogError(
              `Failed to load file ${this._modelHomeDir}${motionFileName}`
            );
            return new ArrayBuffer(0);
          } else {
            // 其他错误情况（如重定向等）
            return new ArrayBuffer(0);
          }
        })
        .then(arrayBuffer => {
          const tmpMotion: CubismMotion = this.loadMotion(
            arrayBuffer,
            arrayBuffer.byteLength,
            name,
            undefined,
            undefined,
            this._modelSetting!,
            group,
            i,
            this._motionConsistency
          );

          if (tmpMotion != null) {
            tmpMotion.setEffectIds(this._eyeBlinkIds, this._lipSyncIds);

            if (this._motions.getValue(name) != null) {
              ACubismMotion.delete(this._motions.getValue(name));
            }

            this._motions.setValue(name, tmpMotion);

            this._motionCount++;
          } else {
            // 如果无法执行 loadMotion，动作总数会出现偏差，因此需减少 1 个
            this._allMotionCount--;
          }

          if (this._motionCount >= this._allMotionCount) {
            this._state = LoadStep.LoadTexture;

            // 停止所有动作
            this._motionManager.stopAllMotions();

            this._updating = false;
            this._initialized = true;

            this.createRenderer();
            this.setupTextures();
            this.getRenderer().startUp(
              this._subdelegate.getGlManager().getGl()
            );
          }
        });
    }
  }

  /**
   * すべてのモーションデータを解放する。
   */
  public releaseMotions(): void {
    this._motions.clear();
  }

  /**
   * 全ての表情データを解放する。
   */
  public releaseExpressions(): void {
    this._expressions.clear();
  }

  /**
   * モデルを描画する処理。モデルを描画する空間のView-Projection行列を渡す。
   */
  public doDraw(): void {
    if (this._model == null) return;

    // キャンバスサイズを渡す
    const canvas = this._subdelegate.getCanvas();
    const viewport: number[] = [0, 0, canvas.width, canvas.height];

    this.getRenderer().setRenderState(
      this._subdelegate.getFrameBuffer(),
      viewport
    );
    this.getRenderer().drawModel();
  }

  /**
   * モデルを描画する処理。モデルを描画する空間のView-Projection行列を渡す。
   */
  public draw(matrix: CubismMatrix44): void {
    if (this._model == null) {
      return;
    }

    // 各読み込み終了後
    if (this._state == LoadStep.CompleteSetup) {
      matrix.multiplyByMatrix(this._modelMatrix);

      this.getRenderer().setMvpMatrix(matrix);

      this.doDraw();
    }
  }

  public async hasMocConsistencyFromFile() {
    CSM_ASSERT(this._modelSetting.getModelFileName().localeCompare(``));

    // CubismModel
    if (this._modelSetting.getModelFileName() != '') {
      const modelFileName = this._modelSetting.getModelFileName();

      const response = await fetch(`${this._modelHomeDir}${modelFileName}`);
      const arrayBuffer = await response.arrayBuffer();

      this._consistency = CubismMoc.hasMocConsistency(arrayBuffer);

      if (!this._consistency) {
        CubismLogInfo('Inconsistent MOC3.');
      } else {
        CubismLogInfo('Consistent MOC3.');
      }

      return this._consistency;
    } else {
      LAppPal.printMessage('Model data does not exist.');
    }
  }

  public setSubdelegate(subdelegate: LAppSubdelegate): void {
    this._subdelegate = subdelegate;
  }

  /**
   * コンストラクタ
   */
  public constructor() {
    super();

    this._modelSetting = null;
    this._modelHomeDir = null;
    this._userTimeSeconds = 0.0;

    this._eyeBlinkIds = new csmVector<CubismIdHandle>();
    this._lipSyncIds = new csmVector<CubismIdHandle>();

    this._motions = new csmMap<string, ACubismMotion>();
    this._expressions = new csmMap<string, ACubismMotion>();

    this._hitArea = new csmVector<csmRect>();
    this._userArea = new csmVector<csmRect>();

    this._idParamAngleX = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamAngleX
    );
    this._idParamAngleY = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamAngleY
    );
    this._idParamAngleZ = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamAngleZ
    );
    this._idParamEyeBallX = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamEyeBallX
    );
    this._idParamEyeBallY = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamEyeBallY
    );
    this._idParamBodyAngleX = CubismFramework.getIdManager().getId(
      CubismDefaultParameterId.ParamBodyAngleX
    );
    this._idParamBodyAngleY = CubismFramework.getIdManager().getId("ParamBodyAngleY");
    this._idParamBodyAngleZ = CubismFramework.getIdManager().getId("ParamBodyAngleZ");
    this._idParamMouthOpenY = CubismFramework.getIdManager().getId("ParamMouthOpenY");
    this._idParamEyeLOpen = CubismFramework.getIdManager().getId("ParamEyeLOpen");
    this._idParamEyeROpen = CubismFramework.getIdManager().getId("ParamEyeROpen");

    if (LAppDefine.MOCConsistencyValidationEnable) {
      this._mocConsistency = true;
    }

    if (LAppDefine.MotionConsistencyValidationEnable) {
      this._motionConsistency = true;
    }

    this._state = LoadStep.LoadAssets;
    this._expressionCount = 0;
    this._textureCount = 0;
    this._motionCount = 0;
    this._allMotionCount = 0;
    this._wavFileHandler = new LAppWavFileHandler();
    this._consistency = false;
  }

  private _subdelegate!: LAppSubdelegate;

  _modelSetting: ICubismModelSetting | null; // モデルセッティング情報
  _modelHomeDir: string | null; // モデルセッティングが置かれたディレクトリ
  _userTimeSeconds: number; // デルタ時間の積算値[秒]

  _eyeBlinkIds: csmVector<CubismIdHandle>; // モデルに設定された瞬き機能用パラメータID
  _lipSyncIds: csmVector<CubismIdHandle>; // モデルに設定されたリップシンク機能用パラメータID

  _motions: csmMap<string, ACubismMotion>; // 読み込まれているモーションのリスト
  _expressions: csmMap<string, ACubismMotion>; // 読み込まれている表情のリスト

  _hitArea: csmVector<csmRect>;
  _userArea: csmVector<csmRect>;

  _idParamAngleX: CubismIdHandle; // パラメータID: ParamAngleX
  _idParamAngleY: CubismIdHandle; // パラメータID: ParamAngleY
  _idParamAngleZ: CubismIdHandle; // パラメータID: ParamAngleZ
  _idParamEyeBallX: CubismIdHandle; // パラメータID: ParamEyeBallX
  _idParamEyeBallY: CubismIdHandle; // パラメータID: ParamEyeBAllY
  _idParamBodyAngleX: CubismIdHandle; // パラメータID: ParamBodyAngleX
  _idParamBodyAngleY: CubismIdHandle; // パラメータID: ParamBodyAngleY
  _idParamBodyAngleZ: CubismIdHandle; // パラメータID: ParamBodyAngleZ
  _idParamMouthOpenY: CubismIdHandle; // パラメータID: ParamMouthOpenY
  _idParamEyeLOpen: CubismIdHandle; // パラメータID: ParamEyeLOpen
  _idParamEyeROpen: CubismIdHandle; // パラメータID: ParamEyeROpen

  _state: LoadStep; // 現在のステータス管理用
  _expressionCount: number; // 表情データカウント
  _textureCount: number; // テクスチャカウント
  _motionCount: number; // モーションデータカウント
  _allMotionCount: number; // モーション総数
  _wavFileHandler: LAppWavFileHandler; //wavファイルハンドラ
  _consistency: boolean; // MOC3整合性チェック管理用
}
