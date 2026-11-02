let
  Kaynak = Elektrik_Tuketimi,
  #"Diğer sütunlar kaldırıldı" = Table.SelectColumns(Kaynak, {"tuketici_turu"}),
  #"Yinelenenler kaldırıldı" = Table.Distinct(#"Diğer sütunlar kaldırıldı", {"tuketici_turu"})
in
  #"Yinelenenler kaldırıldı"
