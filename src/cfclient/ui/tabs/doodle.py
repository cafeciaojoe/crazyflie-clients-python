Position(
    self.wand_pos.x + round(math.cos(math.radians(self.wand_pos.yaw)),4) * self.length_from_wand,
    self.wand_pos.y + round(math.sin(math.radians(self.wand_pos.yaw)),4) * self.length_from_wand,
    ((self.wand_pos.z + round(
        math.sin(
            math.radians(self.wand_pos.pitch)), 4)
      * self.length_from_wand) if
     ((self.wand_pos.z + round(
         math.sin(
             math.radians(self.wand_pos.pitch)), 4)
       * self.length_from_wand) > 0) else 0)))