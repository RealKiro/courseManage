// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2024-2026 courseManage Contributors
/**
 * License 状态管理
 * 前端全局单例
 */
import { reactive } from 'vue'
import api from './api'
import i18n from '@/locales'

const { t } = i18n.global

export const FEATURES = {
  GRADE_TREND: 'grade_trend',
  FEE_MANAGEMENT: 'fee_management',
  SMART_SCHEDULING: 'smart_scheduling',
  WECHAT_NOTIFY: 'wechat_notify',
  SMART_COMMAND: 'smart_command',
  DASHBOARD_VIEW: 'dashboard_view',
  FLOATING_SPHERE: 'floating_sphere',
  DATABASE_MANAGEMENT: 'database_management',
  STUDENT_EVALUATION: 'student_evaluation',
}

export const FEATURE_NAMES = {
  [FEATURES.GRADE_TREND]: 'license.featureGradeTrend',
  [FEATURES.FEE_MANAGEMENT]: 'license.featureFeeManagement',
  [FEATURES.SMART_SCHEDULING]: 'license.featureSmartScheduling',
  [FEATURES.WECHAT_NOTIFY]: 'license.featureWechatNotify',
  [FEATURES.SMART_COMMAND]: 'license.featureSmartCommand',
  [FEATURES.DASHBOARD_VIEW]: 'license.featureDashboardView',
  [FEATURES.FLOATING_SPHERE]: 'license.featureFloatingSphere',
  [FEATURES.DATABASE_MANAGEMENT]: 'license.featureDatabaseManagement',
  [FEATURES.STUDENT_EVALUATION]: 'license.featureStudentEvaluation',
}

export const FEATURE_DESCRIPTIONS = {
  [FEATURES.GRADE_TREND]: {
    highlights: 'license.featureGradeTrendHighlights',
    details: 'license.featureGradeTrendDetails',
  },
  [FEATURES.FEE_MANAGEMENT]: {
    highlights: 'license.featureFeeManagementHighlights',
    details: 'license.featureFeeManagementDetails',
  },
  [FEATURES.SMART_SCHEDULING]: {
    highlights: 'license.featureSmartSchedulingHighlights',
    details: 'license.featureSmartSchedulingDetails',
  },
  [FEATURES.WECHAT_NOTIFY]: {
    highlights: 'license.featureWechatNotifyHighlights',
    details: 'license.featureWechatNotifyDetails',
  },
  [FEATURES.SMART_COMMAND]: {
    highlights: 'license.featureSmartCommandHighlights',
    details: 'license.featureSmartCommandDetails',
  },
  [FEATURES.DASHBOARD_VIEW]: {
    highlights: 'license.featureDashboardViewHighlights',
    details: 'license.featureDashboardViewDetails',
  },
  [FEATURES.FLOATING_SPHERE]: {
    highlights: 'license.featureFloatingSphereHighlights',
    details: 'license.featureFloatingSphereDetails',
  },
  [FEATURES.DATABASE_MANAGEMENT]: {
    highlights: 'license.featureDatabaseManagementHighlights',
    details: 'license.featureDatabaseManagementDetails',
  },
  [FEATURES.STUDENT_EVALUATION]: {
    highlights: 'license.featureStudentEvaluationHighlights',
    details: 'license.featureStudentEvaluationDetails',
  },
}

export const LICENSE_TYPES = {
  trialA:     { name: 'license.trialLicense', days: 3 },
  trialB:     { name: 'license.trialLicense', days: 7 },
  monthly:    { name: 'license.monthlyLicense', days: 30 },
  quarterly:  { name: 'license.quarterlyLicense', days: 90 },
  semiannual: { name: 'license.semiannualLicense', days: 180 },
  annual:     { name: 'license.annualLicense', days: 365 },
  perpetual:  { name: 'license.perpetualLicense', days: null },
}

export const FEATURE_PRICES = {
  [FEATURES.FLOATING_SPHERE]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.SMART_COMMAND]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.DASHBOARD_VIEW]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.WECHAT_NOTIFY]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.GRADE_TREND]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.FEE_MANAGEMENT]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.SMART_SCHEDULING]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.DATABASE_MANAGEMENT]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
  [FEATURES.STUDENT_EVALUATION]: { trialA: 1.99, trialB: 2.99, monthly: 6.99, quarterly: 17.99, semiannual: 29.99, annual: 49.99, perpetual: 196.99 },
}

export function calcTotalPrice(selectedFeatures, licenseType) {
  if (!selectedFeatures.length || !licenseType) return 0
  let total = 0
  for (const feat of selectedFeatures) {
    const priceTable = FEATURE_PRICES[feat]
    if (priceTable && priceTable[licenseType] !== undefined) {
      total += priceTable[licenseType]
    }
  }
  return total
}

// 本部署已放开全部功能门禁，但有些模块并不适用于中小学教务场景，
// 在这里集中关闭。关闭后：菜单、页面按钮、运营大屏图表、快捷球入口
// 以及路由守卫都会自动隐藏/拦截 —— 复用的是各处已有的 hasFeature 判断，
// 不需要逐个文件去删模板，改动面最小。
//
// fee_management：课时费/缴费/退费/催缴。义务教育阶段不向学生按课时收费，
//                 后端 /api/fees/* 接口与相关报表已一并移除。
export const DISABLED_FEATURES = [
  FEATURES.FEE_MANAGEMENT,
]

// 本部署已放开全部高级功能：初始状态即为「已激活 + 全部功能可用」。
// 这样即使 /license/status 请求失败或后端未就绪，路由守卫与界面也不会误锁功能。
const ALL_FEATURES_ENABLED = Object.values(FEATURES)
  .filter((feature) => !DISABLED_FEATURES.includes(feature))
  .reduce((acc, feature) => { acc[feature] = true; return acc }, {})

export const licenseState = reactive({
  loaded: true,
  activated: true,
  licenseType: 'perpetual',
  licenseTypeName: '',
  organizationName: '',
  features: { ...ALL_FEATURES_ENABLED },
  expiryDate: null,
  issuedAt: null,
  machineCode: '',
  trialAvailable: false,
  deactivatedLicenses: [],
  licenseKey: '',
  referralCode: '',
  referralActivated: false,
  referralThreshold: 0,
  discountPercent: 0,
  rebatePercent: 0,
  totalSpending: 0,
  siteName: '',
  contactPerson: '',
  contactPhone: '',
  contactEmail: '',
  contactWechat: '',
})

export async function loadLicenseStatus() {
  try {
    const response = await api.get('/license/status')
    const d = response.data
    // 只同步机构/联系人等展示信息；activated 与 features 恒为全开，
    // 不受后端返回值影响（router/index.js 的守卫直接读这两个字段）。
    Object.assign(licenseState, {
      loaded: true,
      activated: true,
      licenseType: d.license_type || 'perpetual',
      licenseTypeName: d.license_type_name || '',
      organizationName: d.organization_name || '',
      features: { ...ALL_FEATURES_ENABLED },
      expiryDate: null,
      issuedAt: d.issued_at || null,
      machineCode: d.machine_code || '',
      trialAvailable: false,
      deactivatedLicenses: [],
      licenseKey: '',
      referralCode: d.referral_code || '',
      referralActivated: d.referral_activated || false,
      referralThreshold: d.referral_threshold || 0,
      discountPercent: d.discount_percent != null ? d.discount_percent : 0,
      rebatePercent: d.rebate_percent != null ? d.rebate_percent : 0,
      totalSpending: d.total_spending || 0,
      siteName: d.site_name || '',
      contactPerson: d.contact_person || '',
      contactPhone: d.contact_phone || '',
      contactEmail: d.contact_email || '',
      contactWechat: d.contact_wechat || '',
    })
  } catch (error) {
    // 后端不可达时也保持全开，避免误锁
    licenseState.loaded = true
    licenseState.activated = true
    licenseState.features = { ...ALL_FEATURES_ENABLED }
  }
}

// 门禁已移除：除 DISABLED_FEATURES 里被显式关闭的模块外，一律返回 true。
// 保留函数签名，因为 App.vue / FloatingSphere.vue / Dashboard.vue /
// DashboardView.vue / Students.vue 等十余处模板仍在调用它。
export function hasFeature(featureName) {
  return !DISABLED_FEATURES.includes(featureName)
}

export async function activateLicense(licenseKey, selectedFeatures = null, contactInfo = {}) {
  const body = { license_key: licenseKey }
  if (selectedFeatures && selectedFeatures.length) {
    body.selected_features = selectedFeatures
  }
  if (contactInfo.organization_name) body.organization_name = contactInfo.organization_name
  if (contactInfo.contact_person) body.contact_person = contactInfo.contact_person
  if (contactInfo.contact_phone) body.contact_phone = contactInfo.contact_phone
  if (contactInfo.contact_email) body.contact_email = contactInfo.contact_email
  if (contactInfo.contact_wechat) body.contact_wechat = contactInfo.contact_wechat
  if (contactInfo.remarks) body.remarks = contactInfo.remarks
  const response = await api.post('/license/activate', body)
  await loadLicenseStatus()
  return response.data
}

export async function applyLicense(contactInfo, selectedFeatures, applyType = 'new', licenseType = '', referralCode = '') {
  const body = {
    organization_name: contactInfo.organization_name || '',
    contact_person: contactInfo.contact_person || '',
    contact_phone: contactInfo.contact_phone || '',
    contact_email: contactInfo.contact_email || '',
    contact_wechat: contactInfo.contact_wechat || '',
    remarks: contactInfo.remarks || '',
    selected_features: selectedFeatures || [],
    license_type: licenseType || '',
    apply_type: applyType,
    referral_code: referralCode || '',
  }
  const response = await api.post('/license/apply', body)
  return response.data
}

export async function previewAddonLicense(licenseKey) {
  const response = await api.post('/license/preview-addon', { license_key: licenseKey })
  return response.data
}

export async function deactivateLicense() {
  const response = await api.post('/license/deactivate')
  await loadLicenseStatus()
  return response.data
}

export async function deactivateFeature(featureName) {
  const response = await api.post(`/license/deactivate-feature/${featureName}`)
  await loadLicenseStatus()
  return response.data
}

export async function getMachineCode() {
  const response = await api.get('/license/machine-code')
  return response.data.machine_code
}

export async function notifySupplierView(data) {
  const response = await api.post('/license/notify-supplier-view', data)
  return response.data
}

export async function submitFeedback(data) {
  const response = await api.post('/license/feedback', data)
  return response.data
}

export async function requestReplaceLicense(data) {
  const response = await api.post('/license/request-replace', data)
  return response.data
}