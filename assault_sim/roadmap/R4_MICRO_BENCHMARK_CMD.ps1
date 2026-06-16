Set-Location "C:\repos\python\assault"
.\run_train_eval.ps1 
  -Seeds 42 
  -Episodes 20 
  -AutoCompareAgainstBaseline 
  -CompareBaselineReportPath "C:\repos\python\assault\assault_sim\session\reports\sb3_eval\r1_ab_dummy12_s42\metrics_sb3_report_20260611T154815Z.json" 
  -FailOnCompareNoGo:$false
