<template>
  <div class="page-grid">
    <section class="hero-card compact-hero">
      <div class="eyebrow">数据中心</div>
      <h1>业务数据统一管理</h1>
      <p>集中浏览发包方、承包方和业务申请数据，后续可继续接入标准库、GIS 图层和档案索引。</p>
    </section>

    <section class="panel">
      <div class="panel-title">当前数据域</div>
      <div class="quick-link-grid">
        <RouterLink class="quick-link-card" to="/issuers">
          <div class="quick-link-title">发包方管理</div>
          <div class="quick-link-desc">浏览和维护标准 FBF 数据。</div>
        </RouterLink>
        <RouterLink class="quick-link-card" to="/contractors">
          <div class="quick-link-title">承包方管理</div>
          <div class="quick-link-desc">查看承包方与家庭成员信息。</div>
        </RouterLink>
        <RouterLink class="quick-link-card" to="/requests">
          <div class="quick-link-title">业务申请</div>
          <div class="quick-link-desc">跟踪业务申请、流程状态和附件材料。</div>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
