import React, { useEffect } from 'react'
import { UserProfileResponse } from '../../services/api'
import { average } from '../../utils/dashboard'
import DashboardOverview from './DashboardOverview'
import EnvironmentRoadmap from '../Environment/EnvironmentRoadmap'
import { EnvironmentItem } from '../../types/training'
import './Profile.css'

interface ProfileDetailsProps {
  token: string
  profile: UserProfileResponse
  loading: boolean
  /** 훈련 환경 로드맵(준비 중·이 서버에서 닫힘·후속 연구). 작업 화면이 아니라 여기서 보여 준다 (FE-28). */
  environments?: EnvironmentItem[] | null
  onClose: () => void
  onRefresh: () => void
  /** 주면 시트를 학습 현황 제목 위치로 스크롤해서 연다. 시트가 이 제목에 focus 를 준다. */
  progressHeadingRef?: React.RefObject<HTMLHeadingElement>
}

const formatDate = (date: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(date))

const ProfileDetails: React.FC<ProfileDetailsProps> = ({
  token,
  profile,
  loading,
  environments,
  onClose,
  onRefresh,
  progressHeadingRef,
}) => {
  // 완료 0건의 평균은 0점이 아니라 '없음'이다 (설계 문서 5.5).
  const averageScore = average(profile.total_score, profile.missions_completed)

  // 위의 계정 정보는 profile 값으로 바로 그려져 높이가 정해져 있으니 열자마자 한 번 맞추면 된다.
  useEffect(() => {
    progressHeadingRef?.current?.scrollIntoView({ block: 'start' })
  }, [progressHeadingRef])

  return (
    <div className="profile-sheet">
      {/* 머리는 스크롤되지 않는다. 닫기 버튼이 내용과 함께 밀려 올라가면 찾을 수 없다. */}
      <header className="profile-sheet-header">
        <div>
          <h2 id="profile-sheet-title">프로필</h2>
          <p>훈련 기록과 현재 성과를 확인합니다.</p>
        </div>
        <div className="profile-sheet-actions">
          <button className="ui-button small profile-refresh-button" type="button" onClick={onRefresh} disabled={loading}>
            {loading ? '갱신 중...' : '새로고침'}
          </button>
          <button className="ui-button plain small profile-close-button" type="button" onClick={onClose} aria-label="프로필 닫기">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </header>

      <section className="profile-page" aria-labelledby="profile-sheet-title">
        <div className="profile-identity-card">
          <div className="profile-identity-avatar" aria-hidden="true">
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
            {averageScore === null ? (
              <strong className="is-empty">
                <span aria-hidden="true">—</span>
                <small>완료 기록 없음</small>
              </strong>
            ) : (
              <strong>{averageScore}</strong>
            )}
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
              <dd className="profile-mono">{profile.id}</dd>
            </div>
            <div>
              <dt>가입일</dt>
              <dd>{formatDate(profile.created_at)}</dd>
            </div>
          </dl>
        </div>

        <h3 ref={progressHeadingRef} tabIndex={progressHeadingRef ? -1 : undefined} className="profile-section-title">
          학습 현황
        </h3>
        <DashboardOverview token={token} />

        {environments && environments.length > 0 && (
          <>
            <h3 className="profile-section-title">훈련 환경</h3>
            <EnvironmentRoadmap items={environments} />
          </>
        )}
      </section>
    </div>
  )
}

export default ProfileDetails
