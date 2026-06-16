$good = "C:\repos\python\assault\assault_sim\session\reports\sb3_eval\r1_ab_dummy12_s42\metrics_sb3_report_20260611T154815Z.json"
$bad  = "C:\repos\python\assault\assault_sim\session\reports\sb3_eval\fix_turnlock_s42_smoke\metrics_sb3_report_20260612T174444Z.json"

function Get-Node($path) {
  if (-not (Test-Path -Path $path)) {
    throw "No existe el archivo: $path"
  }
  $j = Get-Content -Path $path -Raw | ConvertFrom-Json
  $sideName = @($j.by_side_and_scenario.PSObject.Properties.Name)[0]
  $sideNode = $j.by_side_and_scenario.$sideName
  $scenarioName = @($sideNode.PSObject.Properties.Name)[0]
  $node = $sideNode.$scenarioName
  return @{
    side = $sideName
    scenario = $scenarioName
    node = $node
  }
}

function Num($v) {
  if ($null -eq $v) { return $null }
  return [double]$v
}

function Subtract-Num($badValue, $goodValue) {
  $b = if ($null -eq $badValue) { 0.0 } else { [double]$badValue }
  $g = if ($null -eq $goodValue) { 0.0 } else { [double]$goodValue }
  return ($b - $g)
}

function Get-Metrics($path) {
  $x = Get-Node $path
  $n = $x.node
  $capt = $n.summary.captured_final_counts
  $c4 = if ($capt -and ($capt.PSObject.Properties.Name -contains "4")) { [int]$capt."4" } else { 0 }
  $c5 = if ($capt -and ($capt.PSObject.Properties.Name -contains "5")) { [int]$capt."5" } else { 0 }

  [pscustomobject]@{
    path = $path
    true_win_rate = Num($n.summary.true_win_rate)
    loss_rate = Num($n.summary.loss_rate)
    strategy_stuck_ratio = Num($n.mission.strategy_stuck_ratio)
    vp_entry_missed_rate = Num($n.mission.vp_entry_missed_rate)
    vp_contact_rate = Num($n.mission.vp_contact_rate)
    forced_ratio = Num($n.policy_alignment.forced_ratio)
    captured_4_5 = ($c4 + $c5)
    fallback_to_attack_rate_in_capture = Num($n.mission.fallback_to_attack_rate_in_capture)
    attack_opportunity_cost_near_vp = Num($n.mission.attack_opportunity_cost_near_vp)
  }
}

$g = Get-Metrics $good
$b = Get-Metrics $bad

"=== GOOD ==="
$g | Format-List
"=== BAD ==="
$b | Format-List

"=== DELTA (BAD - GOOD) ==="
[pscustomobject]@{
  true_win_rate_delta = Subtract-Num $b.true_win_rate $g.true_win_rate
  loss_rate_delta = Subtract-Num $b.loss_rate $g.loss_rate
  strategy_stuck_ratio_delta = Subtract-Num $b.strategy_stuck_ratio $g.strategy_stuck_ratio
  vp_entry_missed_rate_delta = Subtract-Num $b.vp_entry_missed_rate $g.vp_entry_missed_rate
  vp_contact_rate_delta = Subtract-Num $b.vp_contact_rate $g.vp_contact_rate
  forced_ratio_delta = Subtract-Num $b.forced_ratio $g.forced_ratio
  captured_4_5_delta = Subtract-Num $b.captured_4_5 $g.captured_4_5
  fallback_to_attack_rate_in_capture_delta = Subtract-Num $b.fallback_to_attack_rate_in_capture $g.fallback_to_attack_rate_in_capture
  attack_opportunity_cost_near_vp_delta = Subtract-Num $b.attack_opportunity_cost_near_vp $g.attack_opportunity_cost_near_vp
} | Format-List

function Get-DetailedDelta($goodPath, $badPath) {
  $goodNode = (Get-Node $goodPath).node
  $badNode = (Get-Node $badPath).node

  $goodCaptureReasons = $goodNode.mission.capture_fallback_reason_counts
  $badCaptureReasons = $badNode.mission.capture_fallback_reason_counts

  "=== CAPTURE FALLBACK REASONS DELTA ==="
  $allReasons = @($goodCaptureReasons.PSObject.Properties.Name + $badCaptureReasons.PSObject.Properties.Name | Select-Object -Unique)
  $reasonRows = @()
  foreach ($reason in $allReasons) {
    $goodCount = if ($goodCaptureReasons -and ($goodCaptureReasons.PSObject.Properties.Name -contains $reason)) { [int]$goodCaptureReasons.$reason } else { 0 }
    $badCount = if ($badCaptureReasons -and ($badCaptureReasons.PSObject.Properties.Name -contains $reason)) { [int]$badCaptureReasons.$reason } else { 0 }
    $reasonRows += [pscustomobject]@{
      Reason = $reason
      GoodCount = $goodCount
      BadCount = $badCount
      Delta = $badCount - $goodCount
    }
  }
  $reasonRows | Format-Table -AutoSize

  $goodBlockProfiles = $goodNode.mission.capture_move_block_profile
  $badBlockProfiles = $badNode.mission.capture_move_block_profile

  "=== CAPTURE MOVE BLOCK PROFILE DELTA ==="
  $allProfiles = @($goodBlockProfiles.PSObject.Properties.Name + $badBlockProfiles.PSObject.Properties.Name | Select-Object -Unique)
  $profileRows = @()
  foreach ($profile in $allProfiles) {
    $goodCount = if ($goodBlockProfiles -and ($goodBlockProfiles.PSObject.Properties.Name -contains $profile)) { [int]$goodBlockProfiles.$profile } else { 0 }
    $badCount = if ($badBlockProfiles -and ($badBlockProfiles.PSObject.Properties.Name -contains $profile)) { [int]$badBlockProfiles.$profile } else { 0 }
    $profileRows += [pscustomobject]@{
      Profile = $profile
      GoodCount = $goodCount
      BadCount = $badCount
      Delta = $badCount - $goodCount
    }
  }
  $profileRows | Format-Table -AutoSize
}

Get-DetailedDelta -goodPath $good -badPath $bad

$trueWinRateDelta = Subtract-Num $b.true_win_rate $g.true_win_rate
$capturedDelta = Subtract-Num $b.captured_4_5 $g.captured_4_5
$vpMissedDelta = Subtract-Num $b.vp_entry_missed_rate $g.vp_entry_missed_rate

$reasons = @()
if ($trueWinRateDelta -le -0.10) { $reasons += "true_win_rate_delta <= -0.10 ($trueWinRateDelta)" }
if ($capturedDelta -le -5) { $reasons += "captured_4_5_delta <= -5 ($capturedDelta)" }
if ($vpMissedDelta -ge 0.15) { $reasons += "vp_entry_missed_rate_delta >= +0.15 ($vpMissedDelta)" }

"=== VERDICT ==="
if ($reasons.Count -gt 0) {
  "NO-GO"
  "Triggers:"
  $reasons | ForEach-Object { " - $_" }
} else {
  "GO"
  "No trigger thresholds exceeded."
}
