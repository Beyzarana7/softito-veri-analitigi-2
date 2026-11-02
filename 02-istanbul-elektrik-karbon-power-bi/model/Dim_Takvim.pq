let
  Kaynak = Elektrik_Tuketimi,
  #"Diğer sütunlar kaldırıldı" = Table.SelectColumns(Kaynak, {"Tarih"}),
  #"Yinelenenler kaldırıldı" = Table.Distinct(#"Diğer sütunlar kaldırıldı", {"Tarih"}),
  #"Yıl eklendi" = Table.AddColumn(#"Yinelenenler kaldırıldı", "Yıl", each Date.Year([Tarih]), type nullable number),
  #"Değiştirilen sütun türü" = Table.TransformColumnTypes(#"Yıl eklendi", {{"Yıl", Int64.Type}}),
  #"Ay eklendi" = Table.AddColumn(#"Değiştirilen sütun türü", "Ay", each Date.Month([Tarih]), type nullable number),
  #"Değiştirilen sütun türü 1" = Table.TransformColumnTypes(#"Ay eklendi", {{"Ay", Int64.Type}}),
  #"Sütunlar yeniden adlandırıldı" = Table.RenameColumns(#"Değiştirilen sütun türü 1", {{"Ay", "Ay_no"}}),
  #"Özel eklendi" = Table.AddColumn(#"Sütunlar yeniden adlandırıldı", "Ay_Adi", each Date.MonthName([Tarih], "tr-TR"))
in
  #"Özel eklendi"
