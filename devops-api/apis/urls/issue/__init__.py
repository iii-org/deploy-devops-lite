from . import view


def issue_url(api, add_resource):
    # Single Issue
    api.add_resource(view.SingleIssue, "/issues", "/issues/<issue_id>")
    api.add_resource(view.SingleIssueV2, "/v2/issues/<issue_id>")
    add_resource(view.SingleIssueV2, "public")
    api.add_resource(view.CreateSingleIssueV2, "/v2/issues")
    add_resource(view.CreateSingleIssueV2, "public")

    # Issue Family
    api.add_resource(view.IssueFamily, "/issue/<issue_id>/family")
    api.add_resource(view.IssueFamilyV2, "/v2/issue/<issue_id>/family")
    add_resource(view.IssueFamilyV2, "public")

    # Issue statistics
    api.add_resource(view.MyIssueStatistics, "/issues/statistics")
    api.add_resource(view.MyIssueStatisticsV2, "/v2/issues/statistics")
    add_resource(view.MyIssueStatisticsV2, "public")

    api.add_resource(view.MyOpenIssueStatistics, "/issues/open_statistics")
    api.add_resource(view.MyOpenIssueStatisticsV2, "/v2/issues/open_statistics")
    add_resource(view.MyOpenIssueStatisticsV2, "public")

    api.add_resource(view.MyIssueWeekStatistics, "/issues/week_statistics")
    api.add_resource(view.MyIssueWeekStatisticsV2, "/v2/issues/week_statistics")
    add_resource(view.MyIssueWeekStatisticsV2, "public")

    api.add_resource(view.MyIssueMonthStatistics, "/issues/month_statistics")
    api.add_resource(view.MyIssueMonthStatisticsV2, "/v2/issues/month_statistics")
    add_resource(view.MyIssueMonthStatisticsV2, "public")

    # Issue relation
    api.add_resource(view.Relation, "/issues/relation", "/issues/relation/<int:relation_id>")
    api.add_resource(view.RelationV2, "/v2/issues/relation")
    add_resource(view.RelationV2, "public")
    api.add_resource(view.RelationDeleteV2, "/v2/issues/relation/<int:relation_id>")
    add_resource(view.RelationDeleteV2, "public")

    # Issue check closable
    api.add_resource(view.CheckIssueClosable, "/issues/<issue_id>/check_closable")
    api.add_resource(view.CheckIssueClosableV2, "/v2/issues/<issue_id>/check_closable")
    add_resource(view.CheckIssueClosableV2, "public")

    api.add_resource(view.ClosableAllV2, "/v2/issues/close_all")
    add_resource(view.ClosableAllV2, "public")
    api.add_resource(view.IssueSonsV2, "/v2/project/<sint:project_id>/issue/sons")
    add_resource(view.IssueSonsV2, "public")

    # Issue commit relation
    api.add_resource(view.IssueCommitRelation, "/issue/relation")
    api.add_resource(view.IssueCommitRelationV2, "/v2/issue/relation")
    add_resource(view.IssueCommitRelationV2, "public")
    api.add_resource(view.SyncIssueFamiliesV2, "/v2/issue/sync_issue_families")
    add_resource(view.SyncIssueFamiliesV2, "public")
