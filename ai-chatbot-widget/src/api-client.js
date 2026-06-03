/**
 * Chat API Client
 * Backend API와 통신하는 클라이언트
 * 
 * Backend API Endpoints:
 * - POST /api/chat - AI 튜터에게 질문
 * - GET /api/missions/status - 진행 중인 미션 상태 조회
 * - POST /api/auth/login - 로그인 (토큰 발급)
 */

class ChatAPIClient {
  /**
   * @param {string} baseURL - Backend API URL (예: http://localhost:8000)
   * @param {string} token - JWT 인증 토큰
   */
  constructor(baseURL, token = null) {
    this.baseURL = baseURL.replace(/\/$/, ''); // 마지막 슬래시 제거
    this.token = token;
    this.maxRetries = 3;
    this.retryDelay = 1000; // 1초
  }

  /**
   * 토큰 설정
   * @param {string} token - JWT 토큰
   */
  setToken(token) {
    this.token = token;
  }

  /**
   * HTTP 요청 헬퍼 (재시도 로직 포함)
   * @private
   */
  async _request(endpoint, options = {}, retryCount = 0) {
    const url = `${this.baseURL}${endpoint}`;
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    // 토큰이 있으면 Authorization 헤더 추가
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const config = {
      ...options,
      headers,
    };

    try {
      const response = await fetch(url, config);

      // 401 Unauthorized - 토큰 만료 또는 인증 실패
      if (response.status === 401) {
        throw new APIError('인증이 필요합니다. 다시 로그인해주세요.', 401, 'UNAUTHORIZED');
      }

      // 403 Forbidden
      if (response.status === 403) {
        throw new APIError('접근 권한이 없습니다.', 403, 'FORBIDDEN');
      }

      // 404 Not Found
      if (response.status === 404) {
        const errorData = await response.json().catch(() => ({}));
        throw new APIError(
          errorData.detail || '요청한 리소스를 찾을 수 없습니다.',
          404,
          'NOT_FOUND'
        );
      }

      // 500 Internal Server Error - 재시도 가능
      if (response.status >= 500) {
        if (retryCount < this.maxRetries) {
          console.warn(`서버 오류 발생, ${retryCount + 1}/${this.maxRetries} 재시도 중...`);
          await this._sleep(this.retryDelay * Math.pow(2, retryCount)); // Exponential backoff
          return this._request(endpoint, options, retryCount + 1);
        }
        throw new APIError('서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.', 500, 'SERVER_ERROR');
      }

      // 기타 에러
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new APIError(
          errorData.detail || `요청 실패: ${response.status}`,
          response.status,
          'REQUEST_FAILED'
        );
      }

      // 성공 응답
      return await response.json();

    } catch (error) {
      // 네트워크 오류 - 재시도 가능
      if (error instanceof TypeError && error.message.includes('fetch')) {
        if (retryCount < this.maxRetries) {
          console.warn(`네트워크 오류, ${retryCount + 1}/${this.maxRetries} 재시도 중...`);
          await this._sleep(this.retryDelay * Math.pow(2, retryCount));
          return this._request(endpoint, options, retryCount + 1);
        }
        throw new APIError(
          '네트워크 연결에 실패했습니다. 인터넷 연결을 확인해주세요.',
          0,
          'NETWORK_ERROR'
        );
      }

      // APIError는 그대로 throw
      if (error instanceof APIError) {
        throw error;
      }

      // 기타 예상치 못한 에러
      throw new APIError(`예상치 못한 오류: ${error.message}`, 0, 'UNKNOWN_ERROR');
    }
  }

  /**
   * Sleep 헬퍼
   * @private
   */
  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * AI 튜터에게 질문 전송
   * 
   * @param {string} message - 사용자 질문
   * @param {number} hintLevel - 힌트 레벨 (0~3)
   * @returns {Promise<ChatResponse>}
   * 
   * Response:
   * {
   *   response: string,      // AI 응답 내용
   *   hint_level: number,    // 힌트 레벨
   *   mission_name: string   // 현재 미션명 (optional)
   * }
   */
  async sendMessage(message, hintLevel = 0) {
    if (!message || message.trim() === '') {
      throw new APIError('메시지를 입력해주세요.', 400, 'INVALID_INPUT');
    }

    if (hintLevel < 0 || hintLevel > 3) {
      throw new APIError('힌트 레벨은 0~3 사이여야 합니다.', 400, 'INVALID_HINT_LEVEL');
    }

    const response = await this._request('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: message.trim(),
        hint_level: hintLevel,
      }),
    });

    return response;
  }

  /**
   * 진행 중인 미션 상태 조회
   * 
   * @returns {Promise<MissionStatus>}
   * 
   * Response:
   * {
   *   attempt: {
   *     id: string,
   *     mission_id: string,
   *     status: string,
   *     hints_used: number,
   *     ...
   *   },
   *   elapsed_seconds: number,
   *   remaining_seconds: number,
   *   current_score: number
   * }
   */
  async getMissionStatus() {
    const response = await this._request('/api/missions/status', {
      method: 'GET',
    });

    return response;
  }

  /**
   * 미션 목록 조회
   * 
   * @returns {Promise<Mission[]>}
   */
  async getMissions() {
    const response = await this._request('/api/missions/', {
      method: 'GET',
    });

    return response;
  }

  /**
   * 로그인 (토큰 발급)
   * 
   * @param {string} username - 사용자명
   * @param {string} password - 비밀번호
   * @returns {Promise<{access_token: string, token_type: string}>}
   */
  async login(username, password) {
    // OAuth2PasswordRequestForm 형식 (application/x-www-form-urlencoded)
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await this._request('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData.toString(),
    });

    // 토큰 자동 설정
    if (response.access_token) {
      this.setToken(response.access_token);
    }

    return response;
  }

  /**
   * 사용자 프로필 조회
   * 
   * @returns {Promise<UserProfile>}
   */
  async getProfile() {
    const response = await this._request('/api/auth/me', {
      method: 'GET',
    });

    return response;
  }

  /**
   * 연결 테스트
   * 
   * @returns {Promise<boolean>}
   */
  async testConnection() {
    try {
      const response = await this._request('/health', {
        method: 'GET',
      });
      return response.status === 'ok';
    } catch (error) {
      console.error('연결 테스트 실패:', error);
      return false;
    }
  }
}

/**
 * API 에러 클래스
 */
class APIError extends Error {
  constructor(message, statusCode, code) {
    super(message);
    this.name = 'APIError';
    this.statusCode = statusCode;
    this.code = code;
  }
}

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ChatAPIClient, APIError };
}
