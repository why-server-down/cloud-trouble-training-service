import React from 'react'
import { UserProfileResponse } from '../../services/api'
import DashboardOverview from './DashboardOverview'
import './Profile.css'

interface ProfileDetailsProps {
  token: string
  profile: UserProfileResponse
  loading: boolean
  onBack: () => void
  onRefresh: () => void
}

const formatDate = (date: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(date))

const ProfileDetails: React.FC<ProfileDetailsProps> = ({ token, profile, loading, onBack, onRefresh }) => {
  const averageScore =
    profile.missions_completed > 0 ? Math.round(profile.total_score / profile.missions_completed) : 0

  return (
    <section className="profile-page">
      <div className="profile-page-header">
        <div>
          <button className="profile-back-button" type="button" onClick={onBack}>
            미션으로 돌아가기
          </button>
          <h2>프로필</h2>
          <p>훈련 기록과 현재 성과를 확인합니다.</p>
        </div>
        <button className="profile-refresh-button" type="button" onClick={onRefresh} disabled={loading}>
          {loading ? '갱신 중...' : '새로고침'}
        </button>
      </div>

      <div className="profile-identity-card">
        <div className="profile-avatar" aria-hidden="true">
          {profile.username.slice(0, 1).toUpperCase()}
        </div>
        <div>
          <h3>{profile.username}</h3>
          <p>가입일 {formatDate(profile.created_at)}</p>
        </div>
      </div>

      <div className="profile-stat-grid">
        <article className="profile-stat-card">
          <span>완료한 미션</span>
          <strong>{profile.missions_completed}</strong>
        </article>
        <article className="profile-stat-card">
          <span>누적 점수</span>
          <strong>{profile.total_score}</strong>
        </article>
        <article className="profile-stat-card">
          <span>평균 점수</span>
          <strong>{averageScore}</strong>
        </article>
      </div>

      <div className="profile-account-card">
        <h3>계정 정보</h3>
        <dl>
          <div>
            <dt>사용자명</dt>
            <dd>{profile.username}</dd>
          </div>
          <div>
            <dt>계정 ID</dt>
            <dd>{profile.id}</dd>
          </div>
          <div>
            <dt>가입일</dt>
            <dd>{formatDate(profile.created_at)}</dd>
          </div>
        </dl>
      </div>
      <DashboardOverview token={token} />
    </section>
  )
}

export default ProfileDetails
