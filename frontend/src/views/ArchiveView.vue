<template>
  <div class="page-grid">
    <section class="hero-card compact-hero">
      <div class="eyebrow">档案管理</div>
      <h1>业务档案与留痕浏览</h1>
      <p>面向流程档案、审核记录和附件材料做集中浏览，后续可继续接入归档目录、卷宗输出和电子档案索引。</p>
    </section>

    <section class="panel">
      <div class="panel-title">档案入口</div>
      <div class="quick-link-grid">
        <RouterLink class="quick-link-card" to="/requests">
          <div class="quick-link-title">业务档案</div>
          <div class="quick-link-desc">查看申请详情、办理轨迹和附件留痕。</div>
        </RouterLink>
        <RouterLink class="quick-link-card" to="/request-attachment-templates">
          <div class="quick-link-title">流程附件</div>
          <div class="quick-link-desc">维护分组模板和节点材料要求。</div>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
