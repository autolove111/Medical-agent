/**
 * WebSocket 服务
 *
 * 职责：
 *   - 管理 WebSocket 连接（连接、断线重连、心跳）
 *   - 提供发送消息和监听事件的接口
 *   - 自动解析服务端推送的 JSON 消息
 *
 * 使用方式：
 *   import wsService from '@/services/wsService'
 *
 *   // 连接
 *   wsService.connect('user_001')
 *
 *   // 监听事件
 *   wsService.on('thought', (data) => console.log(data.content))
 *   wsService.on('tool_call', (data) => console.log(data.name))
 *   wsService.on('final_answer', (data) => console.log(data.answer))
 *
 *   // 发送消息
 *   wsService.send({ type: 'ask', query: '肌酐偏高怎么办' })
 *
 *   // 断开
 *   wsService.disconnect()
 */

class WSService {
  constructor() {
    this.ws = null
    this.userId = null
    this.listeners = {}       // { eventType: [callback, ...] }
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
    this.reconnectDelay = 2000  // 2秒
    this.heartbeatInterval = null
    this.isConnected = false
  }

  /**
   * 建立 WebSocket 连接
   * @param {string} userId - 用户 ID
   */
  connect(userId) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('[WS] Already connected')
      return
    }

    this.userId = userId
    this.reconnectAttempts = 0  // 修复：重置重连计数器

    // 修复：动态构建 WebSocket URL，支持生产环境
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/${userId}`
    console.log('[WS] Connecting to', wsUrl)

    this.ws = new WebSocket(wsUrl)

    this.ws.onopen = () => {
      console.log('[WS] Connected')
      this.isConnected = true
      this.reconnectAttempts = 0
      this._startHeartbeat()
      this._emit('connected', {})
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const type = data.type || 'message'
        this._emit(type, data)
      } catch (e) {
        console.warn('[WS] Parse error:', e, event.data)
      }
    }

    this.ws.onclose = (event) => {
      console.log('[WS] Closed:', event.code, event.reason)
      this.isConnected = false
      this._stopHeartbeat()
      this._emit('disconnected', { code: event.code })

      // 自动重连（指数退避）
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1)
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`)
        setTimeout(() => this.connect(this.userId), delay)
      }
    }

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error)
      this._emit('error', { error })
    }
  }

  /**
   * 断开连接
   */
  disconnect() {
    this.reconnectAttempts = this.maxReconnectAttempts  // 阻止自动重连
    this._stopHeartbeat()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.isConnected = false
    // 修复：不清除 listeners，允许重新连接后继续使用
  }

  /**
   * 发送消息
   * @param {object} data - 要发送的数据（会被 JSON 序列化）
   */
  send(data) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('[WS] Not connected')
      return false
    }
    this.ws.send(JSON.stringify(data))
    return true
  }

  /**
   * 发送用户提问
   * @param {string} query - 用户问题
   * @param {string} sessionId - 会话 ID
   */
  ask(query, sessionId, taskType = 'chat') {
    return this.send({
      type: 'ask',
      query,
      session_id: sessionId,
      task_type: taskType,
    })
  }

  /**
   * 注册事件监听
   * @param {string} eventType - 事件类型
   * @param {function} callback - 回调函数
   */
  on(eventType, callback) {
    if (!this.listeners[eventType]) {
      this.listeners[eventType] = []
    }
    this.listeners[eventType].push(callback)
  }

  /**
   * 移除事件监听
   * @param {string} eventType - 事件类型
   * @param {function} callback - 要移除的回调
   */
  off(eventType, callback) {
    if (!this.listeners[eventType]) return
    this.listeners[eventType] = this.listeners[eventType].filter(cb => cb !== callback)
  }

  /**
   * 移除指定类型的所有监听器
   * @param {string} eventType - 事件类型（可选，不传则清除所有）
   */
  removeAllListeners(eventType) {
    if (eventType) {
      this.listeners[eventType] = []
    } else {
      this.listeners = {}
    }
  }

  /**
   * 触发事件
   * @private
   */
  _emit(eventType, data) {
    const callbacks = this.listeners[eventType] || []
    callbacks.forEach(cb => {
      try {
        cb(data)
      } catch (e) {
        console.error('[WS] Listener error:', e)
      }
    })
  }

  /**
   * 启动心跳
   * @private
   */
  _startHeartbeat() {
    this._stopHeartbeat()
    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected) {
        this.send({ type: 'ping' })
      }
    }, 30000)  // 每 30 秒
  }

  /**
   * 停止心跳
   * @private
   */
  _stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }
}

// 全局单例
const wsService = new WSService()
export default wsService
